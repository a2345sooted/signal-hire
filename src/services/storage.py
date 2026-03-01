import os
import uuid
import logging
import asyncio
import aioboto3
from fastapi import UploadFile, HTTPException
from botocore.exceptions import ClientError
from src.config import settings

logger = logging.getLogger(__name__)

class StorageService:
    def __init__(self):
        self.endpoint_url = settings.s3_endpoint
        self.access_key = settings.s3_access_key
        self.secret_key = settings.s3_secret_key
        self.region_name = settings.s3_region
        self.bucket_name = settings.s3_bucket
        
        self.session = aioboto3.Session(
            aws_access_key_id=self.access_key,
            aws_secret_access_key=self.secret_key,
            region_name=self.region_name
        )

    async def _ensure_bucket_exists(self, s3_client):
        try:
            await s3_client.head_bucket(Bucket=self.bucket_name)
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code')
            if error_code == '404':
                logger.info(f"Bucket {self.bucket_name} does not exist. Creating it...")
                try:
                    if self.region_name == 'us-east-1':
                        await s3_client.create_bucket(Bucket=self.bucket_name)
                    else:
                        await s3_client.create_bucket(
                            Bucket=self.bucket_name,
                            CreateBucketConfiguration={'LocationConstraint': self.region_name}
                        )
                except ClientError as ce:
                    logger.error(f"Failed to create bucket {self.bucket_name}: {ce}")
            else:
                logger.error(f"Error checking bucket {self.bucket_name}: {e}")

    async def upload_file_data(self, file_data: bytes, filename: str, content_type: str = None, dir_id: str = None) -> str:
        """
        Uploads file data to S3.
        If dir_id is provided, stores file as dir_id/filename.
        Otherwise, generates a unique storage key.
        """
        if dir_id:
            storage_key = f"{dir_id}/{filename}"
        else:
            file_extension = os.path.splitext(filename)[1] if filename else ""
            storage_key = f"{uuid.uuid4()}{file_extension}"
        
        try:
            async with self.session.client('s3', endpoint_url=self.endpoint_url) as s3:
                # Optional: ensure bucket exists. In production, buckets are usually pre-created.
                # await self._ensure_bucket_exists(s3)
                
                extra_args = {}
                if content_type:
                    extra_args['ContentType'] = content_type
                
                await s3.put_object(
                    Bucket=self.bucket_name,
                    Key=storage_key,
                    Body=file_data,
                    **extra_args
                )
            return storage_key
        except Exception as e:
            logger.error(f"Failed to upload to S3: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Failed to upload to S3: {str(e)}")

    async def upload_file_data_with_key(self, file_data: bytes, storage_key: str, content_type: str = None) -> str:
        """
        Uploads file data to S3 using the provided storage key.
        """
        try:
            async with self.session.client('s3', endpoint_url=self.endpoint_url) as s3:
                extra_args = {}
                if content_type:
                    extra_args['ContentType'] = content_type
                
                await s3.put_object(
                    Bucket=self.bucket_name,
                    Key=storage_key,
                    Body=file_data,
                    **extra_args
                )
            return storage_key
        except Exception as e:
            logger.error(f"Failed to upload to S3 with key {storage_key}: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Failed to upload to S3: {str(e)}")

    async def upload_file(self, file: UploadFile) -> str:
        try:
            file_data = await file.read()
            return await self.upload_file_data(file_data, file.filename, file.content_type)
        finally:
            try:
                await file.seek(0)
            except Exception:
                pass

    async def delete_file(self, storage_key: str):
        try:
            async with self.session.client('s3', endpoint_url=self.endpoint_url) as s3:
                await s3.delete_object(Bucket=self.bucket_name, Key=storage_key)
        except Exception as e:
            logger.error(f"Failed to delete {storage_key} from S3: {str(e)}")

    async def get_file(self, storage_key: str):
        """
        Returns a StreamingResponse-compatible iterator or the body of the S3 object.
        Note: The caller must manage the lifecycle of the response if needed.
        In FastAPI StreamingResponse, we can pass the body (which is an async stream in aioboto3).
        """
        try:
            # Note: Using a context manager here might close the client before StreamingResponse finishes.
            # However, aioboto3 clients should be used within 'async with'.
            # To handle this for StreamingResponse, we might need a wrapper or use boto3 (sync) 
            # or keep the client open.
            # For simplicity and given the usage in job_handler.py, let's see how it's used.
            s3_client = await self.session.client('s3', endpoint_url=self.endpoint_url).__aenter__()
            response = await s3_client.get_object(Bucket=self.bucket_name, Key=storage_key)
            
            # We return a wrapper that closes the client when the body is closed
            class StreamWrapper:
                def __init__(self, body, client):
                    self.body = body
                    self.client = client
                
                def __aiter__(self):
                    return self.body.__aiter__()
                
                async def read(self, n=-1):
                    return await self.body.read(n)
                
                async def close(self):
                    await self.body.close()
                    await self.client.__aexit__(None, None, None)

            return StreamWrapper(response['Body'], s3_client)
        except Exception as e:
            logger.error(f"Failed to retrieve file from S3: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Failed to retrieve file from S3: {str(e)}")

    async def get_presigned_url(self, storage_key: str, expires_in: int = 3600) -> str:
        """
        Generates a presigned URL for an S3 object.
        """
        try:
            async with self.session.client('s3', endpoint_url=self.endpoint_url) as s3:
                url = await s3.generate_presigned_url(
                    'get_object',
                    Params={'Bucket': self.bucket_name, 'Key': storage_key},
                    ExpiresIn=expires_in
                )
            return url
        except Exception as e:
            logger.error(f"Failed to generate presigned URL: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Failed to generate presigned URL: {str(e)}")

    async def file_exists(self, storage_key: str) -> bool:
        """
        Checks if an object exists in S3.
        """
        try:
            async with self.session.client('s3', endpoint_url=self.endpoint_url) as s3:
                await s3.head_object(Bucket=self.bucket_name, Key=storage_key)
            return True
        except ClientError as e:
            if e.response.get('Error', {}).get('Code') == '404':
                return False
            raise e
        except Exception as e:
            logger.error(f"Failed to check file existence in S3: {str(e)}")
            return False

storage_service = StorageService()

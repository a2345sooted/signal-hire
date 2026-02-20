import os
import uuid

from dotenv import load_dotenv
from fastapi import UploadFile, HTTPException
from minio import Minio

load_dotenv()

class StorageService:
    def __init__(self):
        self.endpoint = os.getenv("MINIO_ENDPOINT", "localhost:9000")
        self.access_key = os.getenv("MINIO_ACCESS_KEY", "minio")
        self.secret_key = os.getenv("MINIO_SECRET_KEY", "minio123")
        self.secure = os.getenv("MINIO_SECURE", "False").lower() == "true"
        
        self.client = Minio(
            self.endpoint,
            access_key=self.access_key,
            secret_key=self.secret_key,
            secure=self.secure
        )
        self.bucket_name = os.getenv("MINIO_BUCKET_NAME", "resumes")
        self._ensure_bucket_exists()

    def _ensure_bucket_exists(self):
        if not self.client.bucket_exists(self.bucket_name):
            self.client.make_bucket(self.bucket_name)

    async def upload_file_data(self, file_data: bytes, filename: str, content_type: str = None, dir_id: str = None) -> str:
        """
        Uploads file data to MinIO.
        If dir_id is provided, stores file as dir_id/filename.
        Otherwise, generates a unique storage key.
        """
        if dir_id:
            storage_key = f"{dir_id}/{filename}"
        else:
            file_extension = os.path.splitext(filename)[1] if filename else ""
            storage_key = f"{uuid.uuid4()}{file_extension}"
        
        try:
            from io import BytesIO
            self.client.put_object(
                self.bucket_name,
                storage_key,
                BytesIO(file_data),
                length=len(file_data),
                content_type=content_type
            )
            return storage_key
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to upload to MinIO: {str(e)}")

    async def upload_file(self, file: UploadFile) -> str:
        try:
            file_data = await file.read()
            return await self.upload_file_data(file_data, file.filename, file.content_type)
        finally:
            try:
                await file.seek(0)
            except Exception:
                # If it's already closed or doesn't support seek, we don't want to crash here
                pass

    def delete_file(self, storage_key: str):
        try:
            self.client.remove_object(self.bucket_name, storage_key)
        except Exception as e:
            # We don't want to fail the whole deletion if MinIO cleanup fails, 
            # but we should probably log it.
            print(f"Failed to delete {storage_key} from MinIO: {str(e)}")

    def get_file(self, storage_key: str):
        try:
            response = self.client.get_object(self.bucket_name, storage_key)
            return response
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to retrieve file from MinIO: {str(e)}")

storage_service = StorageService()

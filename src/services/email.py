import logging
import aioboto3
from src.config import settings

logger = logging.getLogger(__name__)

class EmailService:
    def __init__(self):
        self.region_name = settings.ses_region
        self.access_key = settings.ses_access_key
        self.secret_key = settings.ses_secret_key
        self.sender_email = settings.ses_sender_email
        
        self.session = aioboto3.Session(
            aws_access_key_id=self.access_key,
            aws_secret_access_key=self.secret_key,
            region_name=self.region_name
        )

    async def send_organization_invite(
        self, 
        to_email: str, 
        org_name: str, 
        inviter_email: str, 
        invite_id: str
    ):
        """
        Sends an organization invitation email.
        """
        invite_link = f"{settings.frontend_url}/invites/{invite_id}"
        
        subject = f"Invitation to join {org_name} on Signal"
        body_text = (
            f"You have been invited to join {org_name} by {inviter_email}.\n\n"
            f"Click the link below to accept the invitation:\n"
            f"{invite_link}\n\n"
            f"If you did not expect this invitation, you can safely ignore this email."
        )
        body_html = (
            f"<html>"
            f"<body>"
            f"<h1>Join {org_name}</h1>"
            f"<p>You have been invited to join <strong>{org_name}</strong> by {inviter_email}.</p>"
            f"<p>Click the link below to accept the invitation:</p>"
            f"<p><a href='{invite_link}'>{invite_link}</a></p>"
            f"<p>If you did not expect this invitation, you can safely ignore this email.</p>"
            f"</body>"
            f"</html>"
        )

        try:
            async with self.session.client('ses') as ses:
                response = await ses.send_email(
                    Source=self.sender_email,
                    Destination={
                        'ToAddresses': [to_email]
                    },
                    Message={
                        'Subject': {
                            'Data': subject
                        },
                        'Body': {
                            'Text': {
                                'Data': body_text
                            },
                            'Html': {
                                'Data': body_html
                            }
                        }
                    }
                )
                logger.info(f"Sent invitation email to {to_email}. MessageId: {response['MessageId']}")
                return response['MessageId']
        except Exception as e:
            logger.error(f"Failed to send invitation email to {to_email}: {str(e)}")
            # We don't necessarily want to fail the whole request if email fails, 
            # but for now let's just log it.
            return None

email_service = EmailService()

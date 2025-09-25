import logging
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, Attachment, FileContent, FileName, FileType, Disposition
import base64
from config import settings

# Configurar logging
logger = logging.getLogger(__name__)

def send_verification_code(email: str, code: str):
    """
    Envía un código de verificación por email usando SendGrid
    """
    try:
        subject = "Código de verificación FacturaV"
        body = f"""
        <h2>Verificación de cuenta FacturaV</h2>
        <p>Tu código de verificación es: <strong>{code}</strong></p>
        <p>Este código expirará en 10 minutos.</p>
        """
        
        return send_email(email, subject, body)
        
    except Exception as e:
        logger.error(f"Error enviando código de verificación: {e}")
        return False

def send_email(to_email: str, subject: str, body: str, attachment: bytes = None, filename: str = None):
    """
    Envía un email usando SendGrid API
    """
    try:
        logger.info(f"📧 Enviando email a: {to_email}")
        logger.info(f"📋 Asunto: {subject}")
        
        # Obtener la API key de SendGrid desde settings
        sendgrid_api_key = settings.SENDGRID_API_KEY
        
        if not sendgrid_api_key:
            logger.error("❌ SENDGRID_API_KEY no configurada en settings")
            return False
        
        # Configurar el email FROM
        from_email = settings.FROM_EMAIL
        
        # Crear el objeto Mail
        message = Mail(
            from_email=from_email,
            to_emails=to_email,
            subject=subject,
            html_content=body
        )
        
        # Agregar archivo adjunto si existe
        if attachment and filename:
            logger.info(f"📎 Adjuntando archivo: {filename}")
            
            # Convertir attachment a base64
            if isinstance(attachment, bytes):
                file_content = attachment
            elif hasattr(attachment, 'getvalue'):
                file_content = attachment.getvalue()
            else:
                file_content = str(attachment).encode()
            
            encoded_file = base64.b64encode(file_content).decode()
            
            # Crear attachment
            attached_file = Attachment()
            attached_file.file_content = FileContent(encoded_file)
            attached_file.file_name = FileName(filename)
            attached_file.file_type = FileType('application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
            attached_file.disposition = Disposition('attachment')
            
            message.attachment = attached_file
            logger.info(f"✅ Archivo {filename} preparado para adjuntar")
        
        # Enviar el email
        sg = SendGridAPIClient(sendgrid_api_key)
        response = sg.send(message)
        
        # Verificar respuesta
        if response.status_code == 202:
            logger.info(f"✅ Email enviado exitosamente a {to_email}")
            return True
        else:
            logger.error(f"❌ Error SendGrid: Status {response.status_code}")
            logger.error(f"❌ Respuesta: {response.body}")
            return False
            
    except Exception as e:
        logger.error(f"💥 Error enviando email con SendGrid: {e}")
        return False

def send_email_with_file(to_email: str, subject: str, body: str, file_data=None, filename: str = "factura.xlsx"):
    """
    Versión alternativa que acepta file_data (BytesIO) en lugar de attachment bytes
    """
    try:
        # Convertir file_data a bytes si es necesario
        if file_data:
            if hasattr(file_data, 'getvalue'):
                attachment_bytes = file_data.getvalue()
            else:
                attachment_bytes = file_data
        else:
            attachment_bytes = None
            
        return send_email(to_email, subject, body, attachment_bytes, filename)
        
    except Exception as e:
        logger.error(f"Error en send_email_with_file: {e}")
        return False
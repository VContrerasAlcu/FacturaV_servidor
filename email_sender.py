import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from config import settings

def send_verification_code(email: str, code: str):
    subject = "Código de verificación FacturaV"
    body = f"""
    <h2>Verificación de cuenta FacturaV</h2>
    <p>Tu código de verificación es: <strong>{code}</strong></p>
    <p>Este código expirará en 10 minutos.</p>
    """
    
    send_email(email, subject, body)

def send_email(to_email: str, subject: str, body: str, attachment: bytes = None, filename: str = None):
    try:
        # Configurar el mensaje
        msg = MIMEMultipart()
        msg['From'] = settings.SMTP_USERNAME
        msg['To'] = to_email
        msg['Subject'] = subject
        
        # Adjuntar cuerpo del mensaje
        msg.attach(MIMEText(body, 'html'))
        
        # Adjuntar archivo si existe
        if attachment and filename:
            part = MIMEApplication(attachment)
            part.add_header('Content-Disposition', 'attachment', filename=filename)
            msg.attach(part)
        
        # Conectar y enviar email
        with smtplib.SMTP(settings.SMTP_SERVER, settings.SMTP_PORT) as server:
            server.starttls()
            server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
            server.send_message(msg)
            
    except Exception as e:
        print(f"Error enviando email: {e}")
        raise
import os
import imaplib
import email
from email.mime.text import MIMEText
import openai
import smtplib
from dotenv import load_dotenv

# Carregar as variáveis do .env
load_dotenv()

# Configurações do Gmail e OpenAI obtidas do .env
IMAP_SERVER = os.getenv("IMAP_SERVER", "imap.gmail.com")
IMAP_PORT = int(os.getenv("IMAP_PORT", 993))
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
EMAIL_ACCOUNT = os.getenv("SENDER_EMAIL")
EMAIL_PASSWORD = os.getenv("SENDER_PASSWORD")  # Senha de aplicativo do Gmail
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

openai.api_key = OPENAI_API_KEY

def gerar_resposta(email_content):
    """
    Gera uma resposta profissional e amigável com base no conteúdo do e-mail.
    """
    prompt = f"Responda o seguinte e-mail de forma profissional e amigável:\n\n{email_content}"
    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
        max_tokens=250
    )
    return response.choices[0].message.content.strip()

def enviar_email(destinatario, assunto, corpo):
    """
    Envia um e-mail de texto simples para o destinatário informado.
    """
    remetente = EMAIL_ACCOUNT  # Ex: store@navsupply.com.br
    msg = MIMEText(corpo, 'plain')
    msg['Subject'] = assunto
    msg['From'] = remetente
    msg['To'] = destinatario

    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
        server.starttls()  # Inicia conexão segura
        server.login(remetente, EMAIL_PASSWORD)
        server.send_message(msg)

def buscar_ultimo_email():
    """
    Conecta à conta via IMAP e retorna o último e-mail recebido da caixa de entrada.
    """
    mail = imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT)
    mail.login(EMAIL_ACCOUNT, EMAIL_PASSWORD)
    mail.select("inbox")
    # Usa o critério "ALL" para buscar todos os e-mails
    status, messages = mail.search(None, 'ALL')
    email_ids = messages[0].split()
    if email_ids:
        ultimo_email_id = email_ids[-1]  # Último e-mail recebido
        status, msg_data = mail.fetch(ultimo_email_id, "(RFC822)")
        for response_part in msg_data:
            if isinstance(response_part, tuple):
                msg = email.message_from_bytes(response_part[1])
                return msg, ultimo_email_id, mail
    return None, None, mail

def extrair_conteudo_email(msg):
    """
    Extrai remetente, assunto e corpo do e-mail.
    """
    remetente = msg.get("From")
    subject = msg.get("Subject")
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            content_disposition = str(part.get("Content-Disposition"))
            if content_type == "text/plain" and "attachment" not in content_disposition:
                try:
                    body = part.get_payload(decode=True).decode()
                except Exception as e:
                    body = ""
                break
    else:
        try:
            body = msg.get_payload(decode=True).decode()
        except Exception as e:
            body = ""
    return remetente, subject, body

def marcar_email_como_lido(mail, email_id):
    """
    Marca o e-mail processado como lido.
    """
    mail.store(email_id, '+FLAGS', '\\Seen')

def main():
    # Buscar o último e-mail recebido
    msg, email_id, mail = buscar_ultimo_email()
    if msg:
        remetente, subject, body = extrair_conteudo_email(msg)
        print("Email recebido de:", remetente)
        print("Assunto:", subject)
        print("Corpo:", body)

        # Gerar resposta via ChatGPT com base no conteúdo do e-mail
        resposta = gerar_resposta(body)
        print("Resposta gerada:", resposta)

        # Enviar a resposta para o remetente
        enviar_email(remetente, "Re: " + subject, resposta)
        print("Resposta enviada com sucesso!")

        # Marcar o e-mail como lido
        marcar_email_como_lido(mail, email_id)
    else:
        print("Nenhum e-mail encontrado.")

if __name__ == "__main__":
    main()

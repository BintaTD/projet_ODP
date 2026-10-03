FROM python:3.12-slim

# openssh-client : le SDK Docker s'en sert pour piloter le Docker des workers (ssh://)
RUN apt-get update && apt-get install -y --no-install-recommends \
    openssh-client \
    && rm -rf /var/lib/apt/lists/*

# Configurer SSH pour accepter automatiquement les hôtes distants (évite le prompt interactif / Broken pipe)
RUN echo "    StrictHostKeyChecking no" >> /etc/ssh/ssh_config \
    && echo "    UserKnownHostsFile /dev/null" >> /etc/ssh/ssh_config \
    && echo "    LogLevel ERROR" >> /etc/ssh/ssh_config

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# uid fixe (1000) : la clé SSH montée depuis le controller lui appartient (rôle Ansible docker_remote)
RUN useradd -m -u 1000 flaskuser \
    && mkdir -p /home/flaskuser/.ssh \
    && chown flaskuser:flaskuser /home/flaskuser/.ssh

COPY . .
RUN chown -R flaskuser:flaskuser /app

USER flaskuser

ENV FLASK_APP=run.py
EXPOSE 5000

# Migrations + catalogue des distributions, puis serveur WSGI (pas le serveur de dev Flask)
CMD ["sh", "-c", "flask db upgrade && flask seed && exec gunicorn --bind 0.0.0.0:5000 --workers 2 run:app"]
FROM python:3.12-slim
WORKDIR /app
ENV DEBIAN_FRONTEND=noninteractive
COPY requirements.txt .
# pywinrm's kerberos extra pulls pykerberos, a C extension: it needs a
# toolchain plus krb5-config/headers to build, and links against libkrb5 at
# run time. Runtime packages are installed first so autoremove keeps them,
# then the build-only ones are dropped in the same layer.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      iputils-ping libkrb5-3 libgssapi-krb5-2 krb5-user \
 && apt-get install -y --no-install-recommends \
      gcc libc6-dev libkrb5-dev \
 && pip install --no-cache-dir -r requirements.txt \
 && apt-get purge -y gcc libc6-dev libkrb5-dev \
 && apt-get autoremove -y \
 && rm -rf /var/lib/apt/lists/*
COPY . .
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

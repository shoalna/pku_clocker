FROM python:3
USER root

RUN apt-get -y update

ENV LANG C.UTF-8
ENV TZ Asia/Tokyo

RUN mkdir /api
WORKDIR /api


# pip installs
COPY ./src/requirements.txt .
RUN pip install --upgrade pip
RUN pip install --upgrade setuptools
RUN pip install --no-cache-dir -r requirements.txt

COPY --chmod=755 ./src/app/ .

# Clear
RUN rm -rf /root/.cache /tmp/*

EXPOSE 7778
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "7778", "--workers", "2"]

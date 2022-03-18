FROM registry.access.redhat.com/ubi8

RUN yum install -y httpd

COPY frontend.conf /etc/httpd/conf.d/

RUN rm /etc/httpd/conf.d/welcome.conf

CMD httpd -D FOREGROUND

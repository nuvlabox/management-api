FROM python:3-alpine

ARG GIT_BRANCH
ARG GIT_COMMIT_ID
ARG GIT_BUILD_TIME
ARG GITHUB_RUN_NUMBER
ARG GITHUB_RUN_ID

LABEL git.branch=${GIT_BRANCH}
LABEL git.commit.id=${GIT_COMMIT_ID}
LABEL git.build.time=${GIT_BUILD_TIME}
LABEL git.run.number=${GITHUB_RUN_NUMBER}
LABEL git.run.id=${TRAVIS_BUILD_WEB_URL}

COPY code/ LICENSE /opt/nuvlabox/

WORKDIR /opt/nuvlabox/

RUN apk update && apk add --no-cache curl openssl openssh tini

RUN pip install -r requirements.txt

HEALTHCHECK --interval=10s \
  CMD curl -k https://$(route -n | grep 'UG[ \t]' | awk '{print $2}'):5001 2>&1 | grep SSL || (kill `pgrep tini` && exit 1)

VOLUME /srv/nuvlabox/shared

ONBUILD RUN ./license.sh

ENTRYPOINT ["/sbin/tini", "--"]

CMD ["./app.py"]
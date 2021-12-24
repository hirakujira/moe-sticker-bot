#!/bin/bash

GITHUB_TOKEN=$1

echo "Building moe-sticker-bot for Github Container Registry!"

c1=$(buildah from debian:11)

# install system dependencies
buildah run $c1 -- apt update -y
buildah run $c1 -- apt install python3 python3-pip imagemagick curl libarchive-tools -y

buildah run $c1 -- pip3 install wheel setuptools
buildah run $c1 -- pip3 install python-telegram-bot emoji requests beautifulsoup4

buildah run $c1 -- apt autoremove python3-pip -y
buildah run $c1 -- apt install python3-setuptools -y
buildah run $c1 -- apt autoclean

buildah run $c1 -- curl -Lo /usr/bin/ffmpeg https://github.com/eugeneware/ffmpeg-static/releases/download/b4.4/linux-x64
buildah run $c1 -- chmod +x /usr/bin/ffmpeg

buildah config --cmd '' $c1
buildah config --entrypoint "cd /moe-sticker-bot-master && /usr/bin/python3 main.py" $c1

# Fix python3.8+'s problem.
buildah config --env COLUMNS=80 $c1

buildah commit $c1 moe-sticker-bot

buildah run $c1 -- curl -Lo /moe-sticker-bot.zip https://github.com/star-39/moe-sticker-bot/archive/refs/heads/master.zip
buildah run $c1 -- bsdtar -xvf /moe-sticker-bot.zip -C /

buildah commit $c1 moe-sticker-bot

buildah login -u star-39 -p $GITHUB_TOKEN ghcr.io

buildah push moe-sticker-bot ghcr.io/star-39/moe-sticker-bot:amd64
buildah push moe-sticker-bot ghcr.io/star-39/moe-sticker-bot:latest
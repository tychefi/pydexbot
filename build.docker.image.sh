#!/bin/bash

IMAGE_NAME=${IMAGE_NAME:-"pydexbot:latest"}
docker build $@ -t $IMAGE_NAME .

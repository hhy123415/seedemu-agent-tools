#!/bin/sh
set -eu
cd /app
node /mindcraft/configure.mjs
socat TCP-LISTEN:8081,bind=0.0.0.0,reuseaddr,fork TCP4:127.0.0.1:8080 &
exec node main.js

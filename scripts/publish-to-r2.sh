#!/usr/bin/env bash
set -euo pipefail

publish_dir=${1:?Usage: bash scripts/publish-to-r2.sh <prepared-directory>}
: "${R2_BUCKET_NAME:?R2_BUCKET_NAME must be set}"

# Never delete historical hashes or replace an existing hash with different bytes.
# Rclone infers Content-Type from each filename.
rclone copy "$publish_dir/images" "r2:$R2_BUCKET_NAME/images" \
  --header-upload "Cache-Control: public, max-age=31536000, immutable" \
  --immutable --checksum --fast-list --transfers=16 --checkers=16 --verbose

# set -e stops publication if the image upload fails. Publish the index last.
rclone copy "$publish_dir/templates" "r2:$R2_BUCKET_NAME/templates" \
  --include "*.json" \
  --header-upload "Content-Type: application/json; charset=utf-8" \
  --header-upload "Cache-Control: public, max-age=600" \
  --checksum --verbose

rclone copyto "$publish_dir/manifest.json" "r2:$R2_BUCKET_NAME/manifest.json" \
  --header-upload "Content-Type: application/json; charset=utf-8" \
  --header-upload "Cache-Control: public, max-age=600" \
  --checksum --verbose

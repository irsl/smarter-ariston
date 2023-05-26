#!/bin/bash

unset DEBUG
dir="$(dirname $0)"
actual="$($dir/ocr.py testdata/*.png)"
expected='[null, 50, 51, 42, 53, 44, 45, 46, 47, 48, 49, null, 53, 55, 50, 27, 27, 46, 50, 49, 50, 52, null, 45]'

echo Test finished: testdata/*.png
if [ "$actual" != "$expected" ]; then
  echo "Invalid test results."
  echo "Expected: $expected"
  echo "Actual:   $actual"
  exit 1
fi
echo Green!

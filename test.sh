#!/bin/bash

unset DEBUG
dir="$(dirname $0)"
testfiles="testdata/*.png testdata/*.jpg"
actual="$($dir/ocr.py $testfiles)"
expected='[null, 51, 42, 53, 44, 45, 46, 47, 48, 49, null, 53, 50, 27, 27, 46, 50, 49, 50, 52, 58, 58, 57, 51, 52, 49, 47, 47, 43, null, 45, 26, 27]'

echo Test finished: $testfiles
if [ "$actual" != "$expected" ]; then
  echo "Invalid test results."
  echo "Expected: $expected"
  echo "Actual:   $actual"
  exit 1
fi
echo Green!

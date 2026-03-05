#!/bin/bash

rm -r ./build
mkdir ./build
cd ./build
cmake -DDynamoRIO_DIR=$DYNAMORIO_HOME/cmake ..
make
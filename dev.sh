#!/bin/bash

# Usage: ./dev.sh [mode]
# `./dev.sh` start the container without gpu
# `./dev.sh cuda` start the container with gpu

mode=$1

git submodule update --init --recursive



devname="rtrace-dev"
# check if baffs-dev already running
if [ "$(docker ps -q -f name=$devname)" ]; then
    echo "$devname already exists, connecting to it"
    docker exec -it $devname /bin/zsh
    exit 0
fi

# check if baffs-dev already exists but stopped
if [ "$(docker ps -aq -f status=exited -f name=$devname)" ]; then
    echo "$devname already exists but stopped, starting it"
    docker start $devname
    docker exec -it $devname /bin/zsh
    exit 0
fi

if [ "$mode" == "cuda" ]
then
    echo "Starting $devname with GPU support"
    docker run  -d   --privileged --name $devname --gpus all  -v /tmp/:/tmp  -v $PWD:/home/ubuntu/repos/rtrace  -w /home/ubuntu/repos/rtrace $devname tail -f /dev/null
    echo "====================install CUDA================"
    docker exec -i $devname bash <<EOF
wget https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2204/x86_64/cuda-ubuntu2204.pin
sudo mv cuda-ubuntu2204.pin /etc/apt/preferences.d/cuda-repository-pin-600
wget https://developer.download.nvidia.com/compute/cuda/12.8.0/local_installers/cuda-repo-ubuntu2204-12-8-local_12.8.0-570.86.10-1_amd64.deb
sudo dpkg -i cuda-repo-ubuntu2204-12-8-local_12.8.0-570.86.10-1_amd64.deb
sudo cp /var/cuda-repo-ubuntu2204-12-8-local/cuda-*-keyring.gpg /usr/share/keyrings/
sudo apt-get update
sudo apt-get -y install cuda-toolkit-12-8
EOF
else
    docker run  -d   --privileged --name $devname -v /tmp/:/tmp  -v $PWD:/home/ubuntu/repos/rtrace -w /home/ubuntu/repos/rtrace $devname tail -f /dev/null
fi




echo ============== Install deps ==============
docker exec -i $devname bash <<EOF
/home/ubuntu/miniconda3/envs/rtrace/bin/python -m pip install -r requirements.txt
EOF

# build capstone
echo ============== Building Capstone ==============
docker exec -i $devname bash <<EOF
cd submodules/
cd capstone
./make.sh install
sudo ./make.sh install
EOF

# build nucleus 
echo ============== Building Nucleus ==============
docker exec -i $devname bash <<EOF
cd submodules/
cd nucleus
make clean
make setup
make
cd bindings/python
/home/ubuntu/miniconda3/envs/rtrace/bin/python setup.py install
EOF

echo ============== Building DynamoRio ==============
docker exec -i $devname bash <<EOF
cd submodules/
cd dynamorio 
rm build -r
mkdir build && cd build
cmake ..
make -j
EOF

echo ============= Building FunSeeker ==============
docker exec -i $devname bash <<EOF
cd submodules/
cd FunSeeker
dotnet build -c Release
EOF

echo ============= Building RTrace ==============
docker exec -i $devname bash <<EOF
cd src
./build.sh
EOF

echo ============= Building drltrace ==============
docker exec -i $devname bash <<EOF
cd submodules/
cd drltrace
rm -r build
mkdir build
cd build
cmake -DDynamoRIO_DIR=/home/ubuntu/repos/rtrace/submodules/dynamorio/build/cmake ../drltrace_src
make
ln -s /home/ubuntu/repos/rtrace/submodules/dynamorio/build/ dynamorio
EOF


echo ============= Building libc-test ==============
docker exec -i $devname bash <<EOF
cd submodules/
cd libc-test
make
EOF


docker exec -it $devname /bin/zsh

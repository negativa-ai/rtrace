#!/bin/bash
img=rtrace-dev
ctr=tmp-build
docker rm -f $ctr
docker rmi  $img

docker build -t $img  --build-arg USER_ID=$(id -u ${USER})  --build-arg GROUP_ID=$(id -g ${USER}) .

docker run -i --name $ctr  --entrypoint="" $img bash <<EOF
echo "Types: deb
URIs: http://ddebs.ubuntu.com/
Suites: $(lsb_release -cs) $(lsb_release -cs)-updates $(lsb_release -cs)-proposed 
Components: main restricted universe multiverse
Signed-by: /usr/share/keyrings/ubuntu-dbgsym-keyring.gpg" | \
sudo tee -a /etc/apt/sources.list.d/ddebs.sources
sudo apt update
conda create --prefix /home/ubuntu/miniconda3/envs/rtrace  python=3.9 -y
echo "source /home/ubuntu/miniconda3/bin/activate" >> ~/.zshrc
echo "conda activate rtrace" >> ~/.zshrc
echo "alias c=clear" >> ~/.zshrc
EOF

docker commit $ctr $img
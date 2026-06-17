FROM ubuntu:22.04

ARG USER_ID
ARG GROUP_ID

RUN apt update && apt install sudo -y

# Ubuntu 22.04 has no default `ubuntu` user (24.04 does), so create one matching
# the host UID/GID passed by _docker/build.sh -- this keeps the bind-mounted repo
# (-v $PWD:...) owned correctly. Reuse the group/user if those IDs already exist.
RUN getent group ${GROUP_ID} || groupadd -g ${GROUP_ID} ubuntu
RUN getent passwd ${USER_ID} || useradd -m -u ${USER_ID} -g ${GROUP_ID} -s /bin/bash ubuntu
RUN usermod -aG sudo ubuntu
RUN echo "%sudo ALL=(ALL) NOPASSWD:ALL" >> /etc/sudoers
USER ubuntu

RUN sudo apt update
RUN sudo apt install cmake -y
RUN sudo apt install build-essential -y
RUN sudo apt install python-is-python3 -y
RUN sudo apt install curl -y
RUN sudo apt install wget -y
RUN sudo apt install zsh -y
RUN sudo apt install git -y
RUN sudo apt install time -y
RUN sudo apt install unzip -y
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
RUN . "$HOME/.cargo/env"
RUN sudo mkdir -p /home/ubuntu/
RUN sudo chown ubuntu: -R /home/ubuntu/
RUN mkdir /home/ubuntu/downloads
RUN wget https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh -O /home/ubuntu/downloads/miniconda.sh
RUN bash /home/ubuntu/downloads/miniconda.sh -b -u -p /home/ubuntu/miniconda3
ENV PATH="/home/ubuntu/miniconda3/bin:${PATH}"
RUN sh -c "$(curl -fsSL https://raw.githubusercontent.com/ohmyzsh/ohmyzsh/master/tools/install.sh)"
RUN sudo apt update && sudo apt install psmisc -y
RUN sudo apt install gdb -y
RUN sudo apt install hexedit -y
RUN sudo apt install ubuntu-dbgsym-keyring -y
RUN sudo apt install debian-goodies -y
RUN sudo apt install cmake g++ g++-multilib doxygen git zlib1g-dev libunwind-dev libsnappy-dev liblz4-dev libxxhash-dev -y

# Build env for FunSeeker. Ubuntu 22.04 ships dotnet-sdk-6.0 in its own archive,
# so no packages.microsoft.com repo is needed (unlike 24.04, whose archive only
# has dotnet 8). This matches the build-bundles.yml CI base image.
RUN DEBIAN_FRONTEND=noninteractive TZ=Etc/UTC sudo apt-get install -y dotnet-sdk-6.0


ENV DYNAMORIO_HOME=/home/ubuntu/repos/rtrace/submodules/dynamorio/build
ENV PROJECTPATH=/home/ubuntu/repos/rtrace
ENV PATH="$PATH:/usr/local/cuda/bin/"

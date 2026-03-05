FROM ubuntu:24.04

ARG USER_ID
ARG GROUP_ID

RUN apt update && apt install sudo -y

# existence check for user and group
RUN getent group ${GROUP_ID} 
RUN getent passwd ${USER_ID} 
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

# Build env for FunSeeker
RUN wget https://packages.microsoft.com/config/ubuntu/20.04/packages-microsoft-prod.deb -O /tmp/packages-microsoft-prod.deb && \
    sudo dpkg -i /tmp/packages-microsoft-prod.deb && \
    rm /tmp/packages-microsoft-prod.deb

RUN sudo apt-get update; \
    sudo apt-get install -y apt-transport-https && \
    sudo apt-get update && \
    DEBIAN_FRONTEND=noninteractive TZ=Etc/UTC sudo apt-get install -y dotnet-sdk-6.0


ENV DYNAMORIO_HOME=/home/ubuntu/repos/rtrace/submodules/dynamorio/build
ENV PROJECTPATH=/home/ubuntu/repos/rtrace
ENV PATH="$PATH:/usr/local/cuda/bin/"

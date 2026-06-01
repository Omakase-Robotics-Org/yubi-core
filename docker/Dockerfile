ARG ROS_DISTRO=jazzy
FROM ros:${ROS_DISTRO}-ros-base

ENV DEBIAN_FRONTEND=noninteractive
ENV LANG=C.UTF-8
ENV PIP_BREAK_SYSTEM_PACKAGES=1

ARG ROS_DISTRO=jazzy
ENV ROS_DISTRO=${ROS_DISTRO}

SHELL ["/bin/bash", "-c"]

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        curl \
        git \
        build-essential \
        libboost-all-dev \
        cmake \
        python3-rosdep \
        python3-colcon-common-extensions \
        python3-tk \
        python3-pip && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# external packages (cached before source COPY)
RUN apt-get update -y && \
    apt-get install -y --no-install-recommends \
        ros-$ROS_DISTRO-rmw-cyclonedds-cpp \
        ros-$ROS_DISTRO-ros-base \
        ros-$ROS_DISTRO-ros2bag \
        ros-$ROS_DISTRO-rosbag2-transport \
        ros-$ROS_DISTRO-rosbag2-storage-mcap \
        ros-$ROS_DISTRO-web-video-server && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# install packages for yubi_core
RUN pip install --ignore-installed pip
RUN pip install "airoa_metadata @ git+https://github.com/airoa-org/airoa-metadata.git@development" minio sentry-sdk

# data-backend package (pure Python: GC, upload, state tracking)
COPY ./data-backend /root/ros2_ws/src/data-backend
RUN pip install /root/ros2_ws/src/data-backend

# ROS workspace
RUN mkdir -p /root/ros2_ws/src
COPY ./yubi-core /root/ros2_ws/src/yubi-core
COPY ./airoa_data_msgs /root/ros2_ws/src/airoa_data_msgs
WORKDIR /root/ros2_ws
RUN apt-get update -y && \
    rosdep update && \
    rosdep install --from-paths src --ignore-src -r -y && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*
RUN source /opt/ros/$ROS_DISTRO/setup.bash && \
    colcon build --symlink-install --cmake-args -DCMAKE_BUILD_TYPE=Release && \
    source ./install/setup.bash

COPY ./docker/ros_entrypoint.sh /root/ros_entrypoint.sh
RUN chmod +x /root/ros_entrypoint.sh
RUN echo "source /root/ros_entrypoint.sh" >> /root/.bashrc

ARG GIT_HASH
ARG GIT_BRANCH
ENV GIT_HASH=$GIT_HASH
ENV GIT_BRANCH=$GIT_BRANCH

WORKDIR /root/ros2_ws
CMD ["/bin/bash"]

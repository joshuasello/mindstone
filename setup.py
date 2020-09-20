""" setup.py

"""

import setuptools


with open("README.md", "r") as fh:
    long_description = fh.read()


setuptools.setup(
    name="mindstone",
    package=["mindstone"],
    version="0.1",
    liscence="MIT",
    author="Joshua Sello",
    author_email="joshuasello@gmail.com",
    description="The mindstone python package provides a high-level interface for robot manipulation.",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/joshuasello/mindstone",
    packages=setuptools.find_packages(),
    download_url="https://github.com/joshuasello/mindstone/archive/0.1.tar.gz",
    keywords=["raspberrypi", "microcontroller", "robots", "robot", "control", "mindstone", "microprocessor",
              "mindstone"],
    classifiers=[
        "Programming Language :: Python :: 3",
        'Intended Audience :: Developers',
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires='>=3.8',
)

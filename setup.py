# from distutils.core import setup
from setuptools import setup
from yams import VERSION


def readme():
    with open("README.md", encoding="utf-8") as f:
        return f.read()


setup(
    # Application name:
    name="YAMScrobbler",
    # Version number (initial):
    version=VERSION,
    # Application author details:
    author="Derin Yarsuvat",
    author_email="derin@ml1.net",
    license="GPLv3",
    # Packages
    packages=["yams"],
    package_data={},
    # Include additional files into the package
    include_package_data=False,
    # Details
    url="https://github.com/berulacks/yams",
    download_url="https://github.com/Berulacks/yams/releases/download/{0}/yams-{0}-py3-none-any.whl".format(
        VERSION
    ),
    #
    # license="LICENSE.txt",
    description="Yet Another MPD Scrobbler (for Last.FM!)",
    long_description=readme(),
    long_description_content_type="text/markdown",
    entry_points={"console_scripts": ["yams = yams.__main__:main"]},
    # Dependent packages (distributions)
    install_requires=[
        "python-mpd2>=1.0.0",
        "PyYAML>=5.1",
        "requests>=2.21.0",
        "psutil>=5.6.3",
    ],
    python_requires=">=3",
    zip_safe=False,
)

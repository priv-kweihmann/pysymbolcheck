import setuptools

with open('README.md') as f:
    _long_description = f.read()

requirements = []
with open('requirements.txt') as f:
    requirements = f.read().splitlines()

setuptools.setup(
    name="pysymbolcheck",
    version="2.7",
    author="Konrad Weihmann",
    author_email="kweihmann@outlook.com",
    description="ELF symbol check",
    long_description=_long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/priv-kweihmann/pysymcheck",
    packages=setuptools.find_packages(),
    entry_points={
        "console_scripts": [
            "pysymbolcheck = pysymbolcheck.__main__:main",
        ],
    },
    install_requires=requirements,
    include_package_data=True,
    classifiers=[
        "Development Status :: 4 - Beta",
        "Environment :: Console",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: BSD License",
        "Natural Language :: English",
        "Operating System :: POSIX :: Linux",
        "Programming Language :: Python :: 3 :: Only",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3",
        "Topic :: Software Development :: Quality Assurance",
    ],
    python_requires='>=3.7',
)

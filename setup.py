from setuptools import setup, find_packages

setup(
    name="blog",
    version="0.1.0",
    packages=find_packages(),
    include_package_data=True,
    zip_safe=False,
    install_requires=[
        "Flask==2.3.3",
        "Flask-SQLAlchemy==3.0.5",
    ],
    extras_require={
        "dev": [
            "pytest>=6.2.0",
        ]
    }
)
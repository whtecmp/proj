from setuptools import setup, find_packages

setup(
    name='mypackage',
    version='0.1',
    packages=find_packages(),
    include_package_data=True,
    install_requires=[
        'requests',
        'pydot',
        'graphviz',
        'argparse',
    ],
    entry_points={
        'console_scripts': [
            'mypackage=mypackage.__init__:main',
        ],
    },
    author='Your Name',
    author_email='your.email@example.com',
    description='A simple Python package',
    long_description=open('README.md').read(),
    long_description_content_type='text/markdown',
    url='https://github.com/yourusername/mypackage',
    classifiers=[
        'Programming Language :: Python :: 3',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
    ],
    python_requires='>=3.6',
)

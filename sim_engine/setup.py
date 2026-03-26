from setuptools import find_packages, setup

package_name = "sim_engine"

setup(
    name=package_name,
    version="0.1.0",
    packages=find_packages(exclude=["test"]),
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
    ],
    install_requires=["setuptools", "pyyaml"],
    zip_safe=True,
    maintainer="Chris",
    maintainer_email="chris@todo.com",
    description="CRUCIBLE simulation engine",
    license="MIT",
    entry_points={
        "console_scripts": [
            "sim_engine = sim_engine.node:main",
        ],
    },
)

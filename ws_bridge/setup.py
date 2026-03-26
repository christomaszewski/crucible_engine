from setuptools import find_packages, setup

package_name = "ws_bridge"

setup(
    name=package_name,
    version="0.1.0",
    packages=find_packages(exclude=["test"]),
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
    ],
    install_requires=["setuptools", "websockets"],
    zip_safe=True,
    maintainer="Chris",
    maintainer_email="chris@todo.com",
    description="CRUCIBLE WebSocket bridge between frontend and sim engine",
    license="MIT",
    entry_points={
        "console_scripts": [
            "ws_bridge = ws_bridge.node:main",
        ],
    },
)

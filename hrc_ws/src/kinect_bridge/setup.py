from setuptools import setup

package_name = 'kinect_bridge'

setup(
    name=package_name,
    version='0.1.0',
    packages=[package_name],
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        ('share/' + package_name + '/config', ['config/bridge_params.yaml']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='Duy',
    maintainer_email='duy@experiment.local',
    description='TCP bridge from Windows Kinect C# app to ROS 2',
    license='MIT',
    entry_points={
        'console_scripts': [
            'bridge_node = kinect_bridge.bridge_node:main',
        ],
    },
)

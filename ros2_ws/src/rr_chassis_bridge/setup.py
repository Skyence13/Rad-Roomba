from glob import glob
from setuptools import find_packages, setup

package_name = 'rr_chassis_bridge'
setup(
    name=package_name, version='0.4.0', packages=find_packages(exclude=['test']),
    package_data={},
    data_files=[('share/ament_index/resource_index/packages', ['resource/' + package_name]),
                ('share/' + package_name, ['package.xml']),
    ],
    install_requires=['setuptools'], zip_safe=True,
    maintainer='Robot software', maintainer_email='robot-software@rad-roomba.invalid',
    description='Chassis bridge node (RR-CHS 1.0 host side)', license='Proprietary', tests_require=['pytest'],
    entry_points={'console_scripts': ['chassis_bridge_node = rr_chassis_bridge.node:main']},
)

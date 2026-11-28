from glob import glob
from setuptools import find_packages, setup

package_name = 'rr_bringup'
setup(
    name=package_name, version='0.4.0', packages=find_packages(exclude=['test']),
    package_data={'rr_bringup': ['config/*.yaml']},
    data_files=[('share/ament_index/resource_index/packages', ['resource/' + package_name]),
                ('share/' + package_name, ['package.xml']),
        ('share/' + package_name + '/launch', glob('launch/*.py')),
        ('share/' + package_name + '/config', glob('rr_bringup/config/*.yaml')),
    ],
    install_requires=['setuptools'], zip_safe=True,
    maintainer='Robot software', maintainer_email='robot-software@rad-roomba.invalid',
    description='RobotApp composition, robot node, launch files and configuration', license='Proprietary', tests_require=['pytest'],
    entry_points={'console_scripts': ['robot_node = rr_bringup.robot_node:main']},
)

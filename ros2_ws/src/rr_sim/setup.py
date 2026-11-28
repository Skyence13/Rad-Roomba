from glob import glob
from setuptools import find_packages, setup

package_name = 'rr_sim'
setup(
    name=package_name, version='0.4.0', packages=find_packages(exclude=['test']),
    package_data={},
    data_files=[('share/ament_index/resource_index/packages', ['resource/' + package_name]),
                ('share/' + package_name, ['package.xml']),
    ],
    install_requires=['setuptools'], zip_safe=True,
    maintainer='Robot software', maintainer_email='robot-software@rad-roomba.invalid',
    description='Kinematic trailer simulator, Python protocol fakes on TCP, scenario harness', license='Proprietary', tests_require=['pytest'],
    entry_points={'console_scripts': ['sim_node = rr_sim.sim_node:main', 'sim_server = rr_sim.sim_server:main']},
)

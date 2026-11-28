from glob import glob
from setuptools import find_packages, setup

package_name = 'rr_head_driver'
setup(
    name=package_name, version='0.4.0', packages=find_packages(exclude=['test']),
    package_data={},
    data_files=[('share/ament_index/resource_index/packages', ['resource/' + package_name]),
                ('share/' + package_name, ['package.xml']),
    ],
    install_requires=['setuptools'], zip_safe=True,
    maintainer='Robot software', maintainer_email='robot-software@rad-roomba.invalid',
    description='Head link driver node (head ICD 2.0 link master)', license='Proprietary', tests_require=['pytest'],
    entry_points={'console_scripts': ['head_driver_node = rr_head_driver.node:main']},
)

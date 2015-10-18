.PHONY: all build test clean
.SILENT: test

all: build

clean:
	python setup.py clean

test:
	python setup.py test

dist:
	python setup.py bdist_wheel sdist

build:
	python setup.py build

install:
	python setup.py install

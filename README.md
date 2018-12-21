# rompar

Masked ROM optical data extraction tool.

Latest version:

  https://github.com/SiliconAnalysis/rompar

Original version by Adam Laurie, but significant changes by John
McMaster, Caitlin Morgan, and Jessy Exum.


Rompar is an interactive tool for extracting bianry data out of mask
ROM images. The computer vision method implemented is rather simple,
but has proven useful in several projects. There is still a lot that
can be added to rompar, and pull requests are welcome.

## Usage

To start a new project out of a mask rom image:

```rompar.py <IMAGE> <BITS PER GROUP> <ROWS PER GROUP>```

To open an existing rompar grid project:

```rompar.py --load <GRIDFILE>```

When the rompar python package is installed, `romparqt` should be used
instead of `rompar.py`.

The new QT ui differs greatly from the original project, but the
[original walked through example](http://oamajormal.blogspot.co.uk/2013/01/fun-with-masked-roms.html)
is still useful for seeing what Rompar can do:

For more information, check the tutorial in the help menu, and the
shortcuts on the various menu items inside of Rompar.


Enjoy!
Adam & Rompar contributors.

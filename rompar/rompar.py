from __future__ import print_function
from __future__ import division

from collections import namedtuple
import cv2 as cv
import json
import numpy
import bitarray
import time

BLACK  = (0x00, 0x00, 0x00)
BLUE   = (0xff, 0x00, 0x00)
GREEN  = (0x00, 0xff, 0x00)
YELLOW = (0x00, 0xff, 0xff)
WHITE  = (0xff, 0xff, 0xff)

# create binary printable string
def to_bin(x):
    return ''.join(x & (1 << i) and '1' or '0' for i in range(7, -1, -1))

ImgXY = namedtuple('ImgXY', ['x', 'y'])
BitXY = namedtuple('BitXY', ['x', 'y'])

class Rompar(object):
    def __init__(self, config, img_fn=None, grid_file=None,
                 group_cols=0, group_rows=0):
        self.img_fn = img_fn
        self.grid_file = grid_file
        self.config = config

        self.gui = True

        # Have we attempted to decode bits?
        self.data_read = False

        # Pixels between cols and rows
        self.step_x, self.step_y = (0, 0)
        # Number of rows/cols per bit grouping
        self.group_cols, self.group_rows = (group_cols, group_rows)

        self.Search_HEX = None

        # >= 0 when in edit mode
        self.Edit_x, self.Edit_y = (-1, -1)

        # Global
        self.grid_points_x = []
        self.grid_points_y = []

        grid_json = None
        if self.grid_file:
            with open(self.grid_file, 'r') as gridfile:
                print("loading", self.grid_file)
                grid_json = json.load(gridfile)
            if self.img_fn is None:
                self.img_fn = grid_json.get('img_fn')
            if self.group_cols is None:
                self.group_cols = grid_json.get('group_cols')
                self.group_rows = grid_json.get('group_rows')

            self.grid_points_x = sorted(set(grid_json['grid_points_x']))
            self.grid_points_y = sorted(set(grid_json['grid_points_y']))
            self.config.update(grid_json['config'])

            print ('Grid points: %d x, %d y' % (len(self.grid_points_x),
                                                len(self.grid_points_y)))

            if len(self.grid_points_x) > 1:
                self.step_x = self.grid_points_x[1] - self.grid_points_x[0]
            if len(self.grid_points_y) > 1:
                self.step_y = self.grid_points_y[1] - self.grid_points_y[0]
            if not self.config.default_radius:
                if self.step_x:
                    self.config.radius = self.step_x / 3
                else:
                    self.config.radius = self.step_y / 3

        # Then need critical args
        if not self.img_fn:
            raise Exception("Filename required")
        if not self.group_cols:
            raise Exception("cols required")
        if not self.group_rows:
            raise Exception("rows required")

        #load img as numpy ndarray dimensions (height, width, channels)
        self.img_original = cv.imread(self.img_fn, cv.IMREAD_COLOR)
        print ('Image is %dx%d; %d channels' %
               (self.width, self.height, self.numchannels))

        # Image buffers
        self.img_target = numpy.copy(self.img_original)
        self.img_grid = numpy.zeros(self.img_original.shape, numpy.uint8)
        self.img_peephole = numpy.zeros(self.img_original.shape, numpy.uint8)

        self.__process_target_image()

        self.data = None
        if grid_json and grid_json['data']:
            if (len(self.grid_points_y)*len(self.grid_points_x)) != \
               len(grid_json['data']):
                print("Data length (%d) is different than the number of "
                      "grid intersections (%d). Ignoring data" %
                      (len(data), len(self.grid_points_y)*
                       len(self.grid_points_x)))
            else:
                self.data = bitarray.bitarray(str("".join(grid_json['data'])))
                self.data_read = True

        if self.data is not None:
            self.read_data()

    def redraw_grid(self):
        if not self.gui:
            return

        t = time.time()
        self.img_grid.fill(0)
        self.img_peephole.fill(0)
        print("grid redraw image clear time:", time.time()-t)

        t = time.time()
        self.grid_points_x.sort()
        self.grid_points_y.sort()
        print("grid redraw line sort time:", time.time()-t)

        t = time.time()
        for x in self.grid_points_x:
            cv.line(self.img_grid, (x, 0), (x, self.height), BLUE, 1)
        for y in self.grid_points_y:
            cv.line(self.img_grid, (0, y), (self.width, y), BLUE, 1)
        print("grid line redraw time:", time.time()-t)

        t = time.time()
        for bit_xy in self.iter_bitxy():
            img_xy = self.bitxy_to_imgxy(bit_xy)
            if self.get_data(bit_xy):
                color = GREEN
                if bit_xy.y == self.Edit_y:
                    sx = self.Edit_x - (self.Edit_x % self.group_cols)
                    if sx <= bit_xy.x < (sx + self.group_cols):
                        color = WHITE # highlight if we're in edit mode
            else:
                color = BLUE

            self.grid_draw_circle(img_xy, color, thick=2)
            cv.circle(self.img_peephole, img_xy, self.config.radius + 1, WHITE, -1)
        print("grid circle redraw time:", time.time()-t)

    def render_image(self, img_display=None, rgb=False):
        if img_display is None:
            img_display = numpy.ndarray(self.shape, numpy.uint8)
        else:
            if img_display.shape != self.shape:
                raise ValueError("Image must have the same shape as the Rompar")

        t = time.time()
        if self.config.img_display_blank_image:
            img_display.fill(0)
        elif self.config.img_display_original:
            numpy.copyto(img_display, self.img_original)
        else:
            numpy.copyto(img_display, self.img_target)

        if self.config.img_display_grid:
            self.redraw_grid()
            cv.bitwise_or(img_display, self.img_grid, img_display)

        if self.config.img_display_peephole:
            cv.bitwise_and(img_display, self.img_peephole, img_display)

        if self.config.img_display_data:
            img_hex = self.render_data_layer()
            cv.bitwise_or(img_display, img_hex, img_display)

        print("render_image time:", time.time()-t)

        if rgb:
            cv.cvtColor(img_display, cv.COLOR_BGR2RGB, img_display);

        return img_display

    def read_data(self, force=False):
        # Bail if data is still valid, and we are not forcing a read.
        if self.data_read and not force:
            return

        self.__process_target_image()

        self.data = bitarray.bitarray(
            len(self.grid_points_x)*len(self.grid_points_y))
        self.data.setall(0)

        # maximum possible value if all pixels are set
        maxval = (self.config.radius ** 2) * 255
        print('read_data: max aperture value:', maxval)
        thresh = (maxval / self.config.bit_thresh_div)
        delta = (self.config.radius // 2)

        print('read_data: computing')
        for bit_xy in self.iter_bitxy():
            img_xy = self.bitxy_to_imgxy(bit_xy)
            datasub = self.img_target[img_xy.y - delta:img_xy.y + delta,
                                      img_xy.x - delta:img_xy.x + delta]
            value = datasub.sum(dtype=int)
            self.set_data(bit_xy, value > thresh)

        self.data_read = True

    def get_pixel(self, img_xy):
        img_x, img_y = img_xy
        return self.img_target[img_y, img_x].sum()

    def write_data_as_txt(self, f):
        for bit_y in range(len(self.grid_points_y)):
            if bit_y and bit_y % self.group_rows == 0:
                f.write('\n') # Put a space between row gaps
            for biy_x in range(len(self.grid_points_x)):
                if bit_x and bit_x % self.group_cols == 0:
                    f.write(' ')
                f.write("1" if self.get_data(BitXY(bit_x, bit_y)) else "0")
            f.write('\n') # Newline afer every row

    def write_grid(self, f):
        config = dict(self.config.__dict__)
        config['view'] = config['view'].__dict__

        # XXX: this first cut is partly due to ease of converting old DB
        # Try to move everything non-volatile into config object
        j = {
            # Increment major when a fundamentally breaking change occurs
            # minor reserved for now, but could be used for non-breaking
            'version': (1, 0),
            #'grid_intersections': list(self.iter_grid_intersections()),
            'data': self.data,
            'grid_points_x': self.grid_points_x,
            'grid_points_y': self.grid_points_y,
            'fn': config,
            'group_cols': self.group_cols,
            'group_rows': self.group_rows,
            'config': config,
            'img_fn': self.img_fn,
            }

        json.dump(j, f, indent=4, sort_keys=True)

    def __process_target_image(self):
        #self.config.pix_thresh_min, self.config.dilate, self.config.erode
        t = time.time()
        cv.dilate(self.img_target, (3,3))
        cv.threshold(self.img_original, self.config.pix_thresh_min,
                     0xff, cv.THRESH_BINARY, self.img_target)
        cv.bitwise_and(self.img_target, (0, 0, 255), self.img_target)
        if self.config.dilate:
            cv.dilate(self.img_target, (3,3))
        if self.config.erode:
            cv.erode(self.img_target, (3,3))
        print("process_image time", time.time()-t)

    def get_all_data(self):
        '''Return data as bytes'''
        data = ~self.data if self.config.inverted else self.data
        out = ''
        for column in range(len(self.grid_points_x) // self.group_cols):
            for row in range(len(self.grid_points_y)):
                thischunk = ''
                for x in range(self.group_cols):
                    thisbit = data[x * len(self.grid_points_y) + row +
                                   column * self.group_cols *
                                   len(self.grid_points_y)]
                    thischunk += "1" if thisbit else "0"
                for x in range(self.group_cols // 8):
                    thisbyte = thischunk[x * 8:x * 8 + 8]
                    # reverse self.group_cols if we want LSB
                    if self.config.LSB_Mode:
                        thisbyte = thisbyte[::-1]
                    out += chr(int(thisbyte, 2))
        return out

    def bitxy_to_imgxy(self, bit_xy):
        bit_x, bit_y = bit_xy
        if (0 > bit_x >= len(self.grid_points_x)) or \
           (0 > bit_y >= len(self.grid_points_y)):
            raise IndexError("Bit coodrinate (%d, %d) out of range"%bit_xy)
        return ImgXY(self.grid_points_x[bit_x], self.grid_points_y[bit_y])

    def imgxy_to_bit(self, img_xy):
        return bitxy_to_bit(imgxy_to_bitxy(img_xy))

    def bitxy_to_bit(self, bit_xy):
        bit_x, bit_y = bit_xy
        if (0 > bit_x >= len(self.grid_points_x)) or \
           (0 > bit_y >= len(self.grid_points_y)):
            raise IndexError("Bit coodrinate (%d, %d) out of range"%bit_xy)
        return bit_y + (bit_x * len(self.grid_points_y))

    def imgxy_to_bitxy(self, img_xy, autocenter=True):
        img_x, img_y = img_xy
        if (0 > img_x >= self.width) or (0 > img_y >= self.height):
            raise IndexError("Image coodrinate (%d, %d) out of range"%img_xy)

        if autocenter:
            delta = self.config.radius / 2
            for bit_x, x in enumerate(self.grid_points_x):
                if (x - delta) <= img_x <= (x + delta):
                    for bit_y, y in enumerate(self.grid_points_y):
                        if (y - delta) <= img_y <= (y + delta):
                            return BitXY(bit_x, bit_y)
            raise IndexError("No bit near image coordinate (%d, %d)"%img_xy)
        else:
            try:
                return BitXY(self.grid_points_x.index(img_x),
                             self.grid_points_y.index(img_y))
            except ValueError:
                raise IndexError("No bit at image coordinate (%d, %d)"%img_xy)

    def get_data(self, bit_xy):
        return self.data[self.bitxy_to_bit(bit_xy)]

    def set_data(self, bit_xy, val):
        self.data[self.bitxy_to_bit(bit_xy)] = bool(val)
        return bool(val)

    def toggle_data(self, bit_xy):
        return self.set_data(bit_xy, not self.get_data(bit_xy))

    def update_radius(self):
        if self.config.radius:
            return

        if self.config.default_radius:
            self.config.radius = self.config.default_radius
        else:
            if self.step_x:
                self.config.radius = int(self.step_x / 3)
            elif self.step_y:
                self.config.radius = int(self.step_y / 3)

    def auto_center(self, img_xy):
        '''
        Auto center image global x/y coordinate on contiguous pixel x/y runs
        '''
        img_x, img_y = img_xy
        x_min = img_x
        while self.get_pixel((img_y, x_min)) != 0.0:
            x_min -= 1
        x_max = img_x
        while self.get_pixel((img_y, x_max)) != 0.0:
            x_max += 1
        img_x = x_min + ((x_max - x_min) // 2)
        y_min = img_y
        while self.get_pixel((y_min, img_x)) != 0.0:
            y_min -= 1
        y_max = img_y
        while self.get_pixel((y_max, img_x)) != 0.0:
            y_max += 1
        img_y = y_min + ((y_max - y_min) // 2)
        return ImgXY(img_x, img_y)

    #def draw_Hline(self, img_y, intersections):
    #    cv.line(self.img_grid, (0, img_y), (self.width, img_y), BLUE, 1)
    #    for gridx in self.grid_points_x:
    #        self.grid_draw_circle((gridx, img_y), BLUE)
    #
    #def draw_Vline(self, img_x, intersections):
    #    cv.line(self.img_grid, (img_x, 0), (img_x, self.height), BLUE, 1)
    #    for gridy in self.grid_points_y:
    #        self.grid_draw_circle((img_x, gridy), BLUE)

    def grid_draw_circle(self, img_xy, color, thick=1):
        cv.circle(self.img_grid, img_xy, self.config.radius, BLACK, -1)
        cv.circle(self.img_grid, img_xy, self.config.radius, color, thick)

    def render_data_layer(self):
        if not self.data_read:
            return

        img_hex = numpy.zeros(self.img_original.shape, numpy.uint8)
        dat = self.get_all_data()
        for row in range(len(self.grid_points_y)):
            out = ''
            outbin = ''
            for column in range(len(self.grid_points_x) // self.group_cols):
                thisbyte = ord(dat[column * len(self.grid_points_y) + row])
                hexbyte = '%02X ' % thisbyte
                out += hexbyte
                outbin += to_bin(thisbyte) + ' '
                if self.config.img_display_binary:
                    disp_data = to_bin(thisbyte)
                else:
                    disp_data = hexbyte
                if self.config.img_display_data:
                    if self.Search_HEX and self.Search_HEX.count(thisbyte):
                        textcolor = YELLOW
                    else:
                        textcolor = WHITE

                    cv.putText(
                        img_hex,
                        disp_data,
                        (self.grid_points_x[column * self.group_cols],
                         self.grid_points_y[row] + (self.config.radius // 2) + 1),
                        cv.FONT_HERSHEY_SIMPLEX,
                        self.config.font_size,
                        textcolor)

        return img_hex

    def grid_add_vertical_line(self, img_xy, do_autocenter=True):
        if do_autocenter and not self.get_pixel(img_xy):
            print ('autocenter: miss!')
            return

        if do_autocenter:
            img_xy = self.auto_center(img_xy)

        img_x, img_y = img_xy
        if img_x in self.grid_points_x:
            return

        # only draw a single line if this is the first one
        if len(self.grid_points_x) == 0 or self.group_cols == 1:
            self.grid_points_x.append(img_x)
        else:
            # set up auto draw
            if len(self.grid_points_x) == 1:
                # use a float to reduce rounding errors
                self.step_x = (img_x - self.grid_points_x[0]) / \
                              (self.group_cols - 1)
                # reset stored self.data as main loop will add all entries
                img_x = self.grid_points_x[0]
                self.grid_points_x = []
                self.update_radius()
            # draw a full set of self.group_cols
            for x in range(self.group_cols):
                draw_x = int(img_x + x * self.step_x)
                if draw_x > self.width:
                    break
                self.grid_points_x.append(draw_x)

    def grid_add_horizontal_line(self, img_xy, do_autocenter=True):
        if do_autocenter and not self.get_pixel(img_xy):
            print ('autocenter: miss!')
            return

        if do_autocenter:
            img_xy = self.auto_center(img_xy)

        img_x, img_y = img_xy
        if img_y in self.grid_points_y:
            return

        # only draw a single line if this is the first one
        if len(self.grid_points_y) == 0 or self.group_rows == 1:
            self.grid_points_y.append(img_y)
        else:
            # set up auto draw
            if len(self.grid_points_y) == 1:
                # use a float to reduce rounding errors
                self.step_y = (img_y - self.grid_points_y[0]) / (self.group_rows - 1)
                # reset stored self.data as main loop will add all entries
                img_y = self.grid_points_y[0]
                self.grid_points_y = []
                self.update_radius()
            # draw a full set of self.group_rows
            for y in range(self.group_rows):
                draw_y = int(img_y + y * self.step_y)
                # only draw up to the edge of the image
                if draw_y > self.height:
                    break
                self.grid_points_y.append(draw_y)

    @property
    def width(self):
        return self.shape[1]
    @property
    def height(self):
        return self.shape[0]
    @property
    def numchannels(self):
        return self.shape[2]
    @property
    def shape(self):
        return self.img_original.shape

    def iter_grid_intersections(self):
        for img_x in self.grid_points_x:
            for img_y in self.grid_points_y:
                yield ImgXY(img_x, img_y)

    def iter_bitxy(self):
        for bit_x in range(len(self.grid_points_x)):
            for bit_y in range(len(self.grid_points_y)):
                yield BitXY(bit_x, bit_y)

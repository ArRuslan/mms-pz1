from __future__ import annotations

import math
import os
import zlib
from abc import abstractmethod, ABC
from enum import IntEnum
from io import BytesIO
from typing import BinaryIO, Self

kot_file_path = "/mnt/B0A0B30BA0B2D6D6/kot.PNG"


class PNGChunk(ABC):
    CHUNK_TYPE: str

    @abstractmethod
    def data(self) -> bytes | memoryview:
        ...

    def write(self, fp: BinaryIO) -> None:
        data = self.data()

        fp.write(len(data).to_bytes(4, "big", signed=False))

        crc_buf = PassThroughBytesIO(fp)
        crc_buf.write(self.CHUNK_TYPE.encode("utf8"))
        crc_buf.write(data)

        fp.write(zlib.crc32(crc_buf.getbuffer()).to_bytes(4, "big", signed=False))


class PNGHeader(PNGChunk):
    CHUNK_TYPE = "IHDR"

    def __init__(
            self,
            width: int,
            height: int,
            bit_depth: int,
            color_type: int,
            compression_method: int = 0,
            filter_method: int = 0,
            interlace_method: int = 0,
    ) -> None:
        assert bit_depth in (1, 2, 4, 8, 16)
        assert color_type in (0, 2, 3, 4, 6)
        assert compression_method == 0
        assert filter_method == 0
        assert interlace_method in (0, 1)

        if color_type == 0:
            assert bit_depth in (1, 2, 4, 8, 16)
        elif color_type in (2, 4, 6):
            assert bit_depth in (8, 16)
        elif color_type == 3:
            assert bit_depth in (1, 2, 4, 8)

        self.width = width
        self.height = height
        self.bit_depth = bit_depth
        self.color_type = color_type
        self.compression_method = compression_method
        self.filter_method = filter_method
        self.interlace_method = interlace_method

    def data(self) -> bytes:
        hdr = self.width.to_bytes(4, "big", signed=False)
        hdr += self.height.to_bytes(4, "big", signed=False)
        hdr += bytes([
            self.bit_depth,
            self.color_type,
            self.compression_method,
            self.filter_method,
            self.interlace_method
        ])

        return hdr

    @classmethod
    def read(cls, data: bytes) -> Self:
        return cls(
            width=int.from_bytes(data[0:4], "big", signed=False),
            height=int.from_bytes(data[4:8], "big", signed=False),
            bit_depth=data[8],
            color_type=data[9],
            compression_method=data[10],
            filter_method=data[11],
            interlace_method=data[12],
        )


class PngFilter(IntEnum):
    NONE = 0
    SUB = 1
    UP = 2
    AVERAGE = 3
    PAETH = 4


class PNGData(PNGChunk):
    CHUNK_TYPE = "IDAT"

    def __init__(self, compressed_data: bytes | memoryview) -> None:
        self.compressed_data = compressed_data

    def data(self) -> bytes | memoryview:
        return self.compressed_data

    @classmethod
    def from_pixels(cls, pixels: list[list[Pixel]]) -> Self:
        compressed_data = BytesIO()
        dat_deflate = zlib.compressobj()

        for idx, row in enumerate(pixels):
            line = PngLine(PngFilter.NONE, row, pixels[idx - 1] if idx else None)

            smallest_algo = None
            smallest_pixels = None
            smallest_size = float("inf")

            for cline in (line.none(), line.sub(), line.up(), line.avg(), line.paeth()):
                data = b"".join(bytes(px) for px in cline.pixels)
                comp = zlib.compress(data)
                if len(comp) >= smallest_size:
                    continue
                smallest_algo = cline.filter
                smallest_pixels = cline.pixels
                smallest_size = len(comp)

            compressed_data.write(dat_deflate.compress(bytes([smallest_algo.value])))
            for col in smallest_pixels:
                compressed_data.write(dat_deflate.compress(bytes(col)))

        compressed_data.write(dat_deflate.flush())

        return cls(compressed_data.getbuffer())


class PNGEnd(PNGChunk):
    CHUNK_TYPE = "IEND"

    def data(self) -> bytes | memoryview:
        return b""


def read_png(path: str) -> None:
    dat_inflate = zlib.decompressobj()
    dat = b""
    hdr: PNGHeader | None = None

    with open(path, "rb") as f:
        f.seek(0, os.SEEK_END)
        file_size = f.tell()
        f.seek(0)

        assert f.read(8) == bytes([137, 80, 78, 71, 13, 10, 26, 10])

        while f.tell() < file_size:
            chunk_len = int.from_bytes(f.read(4), "big", signed=False)
            print(f"{chunk_len=!r}")

            chunk_type = f.read(4).decode("utf8")
            print(f"{chunk_type=!r}")

            chunk_data = f.read(chunk_len)
            print(f"{len(chunk_data)=!r}")

            chunk_crc = int.from_bytes(f.read(4), "big", signed=False)
            print(f"{chunk_crc=!r}")

            calculated_chunk_crc = zlib.crc32(chunk_type.encode("utf8") + chunk_data)
            print(f"{calculated_chunk_crc=!r}")

            assert chunk_crc == calculated_chunk_crc

            if chunk_type.lower() == "ihdr":
                assert len(chunk_data) == 13
                hdr = PNGHeader.read(chunk_data)
                print(f"  {hdr.width=!r}")
                print(f"  {hdr.height=!r}")
                print(f"  {hdr.bit_depth=!r}")
                print(f"  {hdr.color_type=!r}")
                print(f"  {hdr.compression_method=!r}")
                print(f"  {hdr.filter_method=!r}")
                print(f"  {hdr.interlace_method=!r}")
            elif chunk_type.lower() == "idat":
                dat += dat_inflate.decompress(chunk_data)
            elif chunk_type.lower() == "iend":
                dat += dat_inflate.flush()
                assert f.tell() == file_size
            else:
                print("unknown chunk, not parsing")

            print("-"*32)

    print(f"decompressed: {len(dat)}")

    assert (hdr.color_type & 1) == 0, "Pallets are not supported"
    assert hdr.color_type == 6, "Only Color+Alpha images are supported!"

    dat_stream = BytesIO(dat)

    with open("test_kot.ppm", "w") as f:
        f.write("P6\n")
        f.write(f"{hdr.width} {hdr.height}\n")
        f.write("255\n")

        for row in range(hdr.height):
            filter_type = dat_stream.read(1)[0]
            pixels = dat_stream.read(int(hdr.width * 4 * hdr.bit_depth / 8))

            for col in range(hdr.width):
                if col % 16 == 0:
                    f.write(f"# row {row}, col {col}\n")
                pixel_r, pixel_g, pixel_b = pixels[col * 4:(col + 1) * 4 - 1]
                f.write(f"{pixel_r} {pixel_g} {pixel_b}\n")

            print(f"row #{row}: {filter_type=!r}, {len(pixels)=!r}")

    print(f"leftover data: {dat_stream.read()}")


class Pixel:
    __slots__ = ("r", "g", "b")

    def __init__(self, r: int, g: int, b: int) -> None:
        self.r = r
        self.g = g
        self.b = b

    def set(self, r: int | None = None, g: int | None = None, b: int | None = None) -> None:
        if r is not None:
            self.r = r
        if g is not None:
            self.g = g
        if b is not None:
            self.b = b

    def __bytes__(self) -> bytes:
        return bytes([self.r, self.g, self.b])


class PngLine:
    def __init__(
            self, filter_: PngFilter, pixels: list[Pixel],
            up_pixels: list[Pixel] | None,
    ) -> None:
        self.filter = filter_
        self.pixels = pixels
        self.up_pixels = up_pixels

    def none(self) -> PngLine:
        if self.filter is PngFilter.NONE:
            return PngLine(PngFilter.NONE, self.pixels.copy(), self.up_pixels)
        elif self.filter is PngFilter.SUB:
            pixels = self._decode_sub()
        elif self.filter is PngFilter.UP:
            pixels = self._decode_up()
        elif self.filter is PngFilter.AVERAGE:
            pixels = self._decode_avg()
        elif self.filter is PngFilter.PAETH:
            pixels = self._decode_paeth()
        else:
            raise RuntimeError("Unreachable")

        return PngLine(PngFilter.NONE, pixels, self.up_pixels)

    def sub(self) -> PngLine:
        if self.filter is PngFilter.SUB:
            return PngLine(PngFilter.SUB, self.pixels.copy(), self.up_pixels)

        none = self.none()

        out = []
        for i, p in enumerate(none.pixels):
            if i == 0:
                out.append(Pixel(p.r, p.g, p.b))
            else:
                left = none.pixels[i - 1]
                out.append(Pixel(
                    (p.r - left.r) % 256,
                    (p.g - left.g) % 256,
                    (p.b - left.b) % 256,
                ))

        return PngLine(PngFilter.SUB, out, self.up_pixels)

    def _decode_sub(self) -> list[Pixel]:
        out = []

        for i, (dr, dg, db) in enumerate(self.pixels):
            if i == 0:
                out.append(Pixel(dr, dg, db))
            else:
                left = out[i - 1]
                out.append(Pixel(
                    (dr + left.r) & 0xFF,
                    (dg + left.g) & 0xFF,
                    (db + left.b) & 0xFF
                ))

        return out

    def up(self) -> PngLine:
        if self.filter is PngFilter.UP or self.up_pixels is None:
            return PngLine(PngFilter.UP, self.pixels.copy(), self.up_pixels)

        none = self.none()

        out = []
        for p, a in zip(none.pixels, none.up_pixels):
            out.append(Pixel(
                (p.r - a.r) % 256,
                (p.g - a.g) % 256,
                (p.b - a.b) % 256,
            ))

        return PngLine(PngFilter.UP, out, self.up_pixels)

    def _decode_up(self) -> list[Pixel]:
        out = []

        if self.up_pixels is None:
            return self.pixels.copy()

        for (dr, dg, db), a in zip(self.pixels, self.up_pixels):
            out.append(Pixel(
                (dr + a.r) & 0xFF,
                (dg + a.g) & 0xFF,
                (db + a.b) & 0xFF
            ))

        return out

    def avg(self) -> PngLine:
        if self.filter is PngFilter.AVERAGE:
            return PngLine(PngFilter.AVERAGE, self.pixels.copy(), self.up_pixels)

        none = self.none()

        out = []
        for x, p in enumerate(none.pixels):
            if x == 0 and self.up_pixels is None:
                avg = (0, 0, 0)
            elif x == 0:
                above = none.up_pixels[x]
                avg = (above.r // 2, above.g // 2, above.b // 2)
            elif self.up_pixels is None:
                left = none.pixels[x - 1]
                avg = (left.r // 2, left.g // 2, left.b // 2)
            else:
                left = none.pixels[x - 1]
                above = self.up_pixels[x]
                avg = ((left.r + above.r) // 2,
                       (left.g + above.g) // 2,
                       (left.b + above.b) // 2)
            out.append(Pixel(
                (p.r - avg[0]) % 256,
                (p.g - avg[1]) % 256,
                (p.b - avg[2]) % 256,
            ))

        return PngLine(PngFilter.AVERAGE, out, self.up_pixels)

    def _decode_avg(self) -> list[Pixel]:
        out = []

        for x, (dr, dg, db) in enumerate(self.pixels):
            if x == 0 and self.up_pixels is None:
                avg = (0, 0, 0)
            elif x == 0:
                above = self.up_pixels[x]
                avg = (above.r // 2, above.g // 2, above.b // 2)
            elif self.up_pixels is None:
                left = out[x - 1]
                avg = (left.r // 2, left.g // 2, left.b // 2)
            else:
                left = out[x - 1]
                above = self.up_pixels[x]
                avg = ((left.r + above.r) // 2,
                       (left.g + above.g) // 2,
                       (left.b + above.b) // 2)

            out.append(Pixel(
                (dr + avg[0]) & 0xFF,
                (dg + avg[1]) & 0xFF,
                (db + avg[2]) & 0xFF
            ))

        return out

    @staticmethod
    def _paeth_predictor(a: int, b: int, c: int) -> int:
        p = a + b - c
        pa = abs(p - a)
        pb = abs(p - b)
        pc = abs(p - c)
        if pa <= pb and pa <= pc:
            return a
        elif pb <= pc:
            return b
        else:
            return c

    def paeth(self) -> PngLine:
        if self.filter is PngFilter.PAETH or self.up_pixels is None:
            return PngLine(PngFilter.PAETH, self.pixels.copy(), self.up_pixels)

        none = self.none()

        out = []
        for x, p in enumerate(none.pixels):
            if x == 0 and self.up_pixels is None:
                pr = pg = pb = 0
            elif x == 0:
                a = self.up_pixels[x]
                pr = a.r
                pg = a.g
                pb = a.b
            elif self.up_pixels is None:
                l = none.pixels[x - 1]
                pr = l.r
                pg = l.g
                pb = l.b
            else:
                l = none.pixels[x - 1]
                a = self.up_pixels[x]
                ul = self.up_pixels[x - 1]
                pr = self._paeth_predictor(l.r, a.r, ul.r)
                pg = self._paeth_predictor(l.g, a.g, ul.g)
                pb = self._paeth_predictor(l.b, a.b, ul.b)

            out.append(Pixel(
                (p.r - pr) % 256,
                (p.g - pg) % 256,
                (p.b - pb) % 256,
            ))

        return PngLine(PngFilter.PAETH, out, self.up_pixels)

    def _decode_paeth(self) -> list[Pixel]:
        out = []

        for x, (dr, dg, db) in enumerate(self.pixels):
            if x == 0 and self.up_pixels is None:
                pr = pg = pb = 0
            elif x == 0:
                a = self.up_pixels[x]
                pr = a.r
                pg = a.g
                pb = a.b
            elif self.up_pixels is None:
                l = out[x - 1]
                pr = l.r
                pg = l.g
                pb = l.b
            else:
                l = out[x - 1]
                a = self.up_pixels[x]
                ul = self.up_pixels[x - 1]
                pr = self._paeth_predictor(l.r, a.r, ul.r)
                pg = self._paeth_predictor(l.g, a.g, ul.g)
                pb = self._paeth_predictor(l.b, a.b, ul.b)

            out.append(Pixel(
                (dr + pr) & 0xFF,
                (dg + pg) & 0xFF,
                (db + pb) & 0xFF
            ))

        return out


class PassThroughBytesIO(BytesIO):
    def __init__(self, back_fp: BinaryIO) -> None:
        super().__init__()
        self._back_fp = back_fp

    def write(self, data: bytes | memoryview) -> None:
        super().write(data)
        self._back_fp.write(data)


def write_png(path: str, pixels: list[list[Pixel]]) -> None:
    with open(path, "wb") as f:
        f.write(bytes([137, 80, 78, 71, 13, 10, 26, 10]))

        PNGHeader(len(pixels[0]), len(pixels), 8, 2).write(f)
        PNGData.from_pixels(pixels).write(f)
        PNGEnd().write(f)


class ImageObject(ABC):
    @abstractmethod
    def render(self, pixels: list[list[Pixel]]) -> None:
        ...


class ImageEllipse(ImageObject):
    def __init__(
            self,
            x: int,
            y: int,
            a: int,
            b: int,
            outer_color: tuple[int, int, int],
            inner_color: tuple[int, int, int],
            border_size: int = 3,
            rotation_deg: int = 0,
    ) -> None:
        self.x = x
        self.y = y
        self.a = a
        self.b = b
        self.outer_color = outer_color
        self.inner_color = inner_color
        self.border_size = border_size
        self.rotation_deg = rotation_deg

    def render(self, pixels: list[list[Pixel]]) -> None:
        height = len(pixels)
        width = len(pixels[0])

        cos_t = math.cos(self.rotation_deg * math.pi / 180)
        sin_t = math.sin(self.rotation_deg * math.pi / 180)
        delta = self.border_size / max(self.a, self.b)

        half_width = math.sqrt((self.a * cos_t) ** 2 + (self.b * sin_t) ** 2)
        half_height = math.sqrt((self.a * sin_t) ** 2 + (self.b * cos_t) ** 2)

        xmin = int(self.x - half_width) - self.border_size
        xmax = int(self.x + half_width) + self.border_size
        ymin = int(self.y - half_height) - self.border_size
        ymax = int(self.y + half_height) + self.border_size

        for y in range(max(0, ymin), min(height, ymax)):
            for x in range(max(0, xmin), min(width, xmax)):
                dx = x - self.x
                dy = y - self.y
                x_p = dx * cos_t + dy * sin_t
                y_p = -dx * sin_t + dy * cos_t
                v = (x_p ** 2) / (self.a ** 2) + (y_p ** 2) / (self.b ** 2)

                if v > 1 + delta:
                    continue

                if v >= 1 - delta:
                    pixels[y][x].set(*self.outer_color)
                else:
                    pixels[y][x].set(*self.inner_color)


class ImageCircle(ImageEllipse):
    def __init__(
            self,
            x: int,
            y: int,
            r: int,
            outer_color: tuple[int, int, int],
            inner_color: tuple[int, int, int],
            border_size: int = 3,
    ) -> None:
        super().__init__(x, y, r, r, outer_color, inner_color, border_size, 0)


class ImageLine(ImageObject):
    def __init__(
            self,
            x0: int,
            y0: int,
            x1: int,
            y1: int,
            color: tuple[int, int, int],
            size: int = 3,
    ) -> None:
        self.x0 = x0
        self.y0 = y0
        self.x1 = x1
        self.y1 = y1
        self.color = color
        self.size = size

    def render(self, pixels: list[list[Pixel]]) -> None:
        dx = abs(self.x1 - self.x0)
        dy = abs(self.y1 - self.y0)
        sx = 1 if self.x0 < self.x1 else -1
        sy = 1 if self.y0 < self.y1 else -1
        err = dx - dy

        x0 = self.x0
        y0 = self.y0

        while True:
            for y in range(math.floor(y0 - self.size / 2), math.ceil(y0 + self.size / 2)):
                for x in range(math.floor(x0 - self.size / 2), math.ceil(x0 + self.size / 2)):
                    pixels[y][x].set(*self.color)
            if x0 == self.x1 and y0 == self.y1:
                break
            e2 = 2 * err
            if e2 > -dy:
                err -= dy
                x0 += sx
            if e2 < dx:
                err += dx
                y0 += sy


class ImageRectangle(ImageObject):
    def __init__(
            self,
            x: int,
            y: int,
            a: int,
            b: int,
            outer_color: tuple[int, int, int],
            inner_color: tuple[int, int, int],
            border_size: int = 3,
            rotation_deg: int = 0,
    ) -> None:
        self.x = x
        self.y = y
        self.a = a
        self.b = b
        self.outer_color = outer_color
        self.inner_color = inner_color
        self.border_size = border_size
        self.rotation_deg = rotation_deg

    def render(self, pixels: list[list[Pixel]]) -> None:
        h = len(pixels)
        w = len(pixels[0])

        cos_t = math.cos(self.rotation_deg * math.pi / 180)
        sin_t = math.sin(self.rotation_deg * math.pi / 180)
        hw = self.a / 2.0
        hh = self.b / 2.0
        t = self.border_size

        half_w = abs(hw * cos_t) + abs(hh * sin_t)
        half_h = abs(hw * sin_t) + abs(hh * cos_t)

        xmin = int(self.x - half_w) - self.border_size
        xmax = int(self.x + half_w) + self.border_size
        ymin = int(self.y - half_h) - self.border_size
        ymax = int(self.y + half_h) + self.border_size

        for py in range(max(0, ymin), min(h, ymax)):
            for px in range(max(0, xmin), min(w, xmax)):
                dx = px - self.x
                dy = py - self.y
                xp = dx * cos_t + dy * sin_t
                yp = -dx * sin_t + dy * cos_t

                if abs(xp) <= hw and abs(yp) <= hh:
                    if (hw - abs(xp) <= t) or (hh - abs(yp) <= t):
                        pixels[py][px].set(*self.outer_color)
                    else:
                        pixels[py][px].set(*self.inner_color)


class Image:
    def __init__(self, width: int, height: int, bg_color: tuple[int, int, int] = (255, 255, 255)) -> None:
        self.width = width
        self.height = height
        self.bg_color = bg_color
        self._objects: list[ImageObject] = []

    def add_object(self, obj: ImageObject) -> None:
        self._objects.append(obj)

    def render(self, file_path: str) -> None:
        pixels = [
            [Pixel(*self.bg_color) for _ in range(self.width)]
            for _ in range(self.height)
        ]

        for obj in self._objects:
            obj.render(pixels)

        write_png(file_path, pixels)


def main() -> None:
    #read_png(kot_file_path)

    img = Image(512, 512)
    img.add_object(ImageEllipse(100, 100, 50, 25, (255, 0, 0), (0, 255, 0), rotation_deg=45))
    img.add_object(ImageCircle(100, 100, 30, (255, 0, 255), (0, 0, 255), 5))
    img.add_object(ImageLine(200, 200, 200, 250, (0, 0, 255), 3))
    img.add_object(ImageLine(200, 250, 250, 250, (0, 0, 255), 3))
    img.add_object(ImageLine(250, 250, 250, 200, (0, 0, 255), 3))
    img.add_object(ImageLine(250, 200, 200, 200, (0, 0, 255), 3))
    img.add_object(ImageRectangle(300, 300, 64, 128, (0, 0, 255), (0, 255, 255), 3, 45))
    img.render("test_render.png")


if __name__ == "__main__":
    main()

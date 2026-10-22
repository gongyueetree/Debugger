"""Pack an RP2040 flash BIN using the UF2 layout in Pico SDK uf2.h."""
import argparse, struct
from pathlib import Path

def convert(data):
    if not data or len(data)>8*1024*1024:raise ValueError('Expected a nonempty RP2040 flash image ≤8 MiB')
    blocks=(len(data)+255)//256
    return b''.join(struct.pack('<8I',0x0a324655,0x9e5d5157,0x2000,0x10000000+i*256,256,i,blocks,0xe48bff56)
        +data[i*256:(i+1)*256].ljust(256,b'\0')+b'\0'*220+struct.pack('<I',0x0ab16f30) for i in range(blocks))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('bin');p.add_argument('uf2');a=p.parse_args()
    Path(a.uf2).write_bytes(convert(Path(a.bin).read_bytes()))

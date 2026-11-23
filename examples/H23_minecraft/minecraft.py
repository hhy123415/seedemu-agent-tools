#!/usr/bin/env python3
"""Add one Minecraft Java server to the shared H00 mini Internet with DNS."""

import argparse
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))

from seedemu.compiler import Docker, Platform
from seedemu.containerBundle import InternetMap
from bundles.MinecraftBundle import MinecraftBundle
from examples.H00_mini_internet import build_emulator


def build_world():
    """Create H23 networking and DNS before rendering, allowing extra services."""
    emu = build_emulator()
    emu.getLayer('DomainNameService').getZone('com.').addRecord('minecraft A 10.170.0.10')
    return emu


def create_minecraft(emu, *, host_port=25565, volume='minecraft-example-data'):
    """Use the same server configuration in H23 and derived experiments."""
    return (MinecraftBundle(emu)
            .enableHostAccess(host_port)
            .setDataVolume(volume))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=HERE / 'output')
    parser.add_argument('--host-port', type=int, default=25565)
    args = parser.parse_args()
    if not 1 <= args.host_port <= 65535:
        parser.error('host-port must be between 1 and 65535')

    emu = build_world()
    emu.render()
    minecraft = create_minecraft(emu, host_port=args.host_port)
    minecraft.addInternalNetwork('170', 'net0', ['10.170.0.10'], '10.170.0.254')
    compiler = Docker(platform=Platform.AMD64)
    minecraft.registerVolumes(compiler)
    compiler.addContainerBundle(minecraft)
    internet_map = InternetMap(emu)
    internet_map.setPorts([8081, 8080, 8082])
    compiler.addContainerBundle(internet_map)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    emu.compile(compiler, str(args.output.resolve()), override=True)


if __name__ == '__main__':
    main()

"""LA_RP2040 board profiles, binary acquisition and portable capture exports.

Only the board-specific firmware profiles are allowed to acquire data. No probes
are sent during enumeration. Protocol fields and sample order are explicit.
"""
from __future__ import annotations
import io, math, struct, time, zipfile

LOGIC_PRODUCT = 'LA-RP2040 SUMP8 v1'
ADC_PRODUCT = 'LA-RP2040 ADC12 v1'
DAP_PRODUCT = 'LA-RP2040 CMSIS-DAP'
LOGIC_RATES = (100000, 200000, 500000, 1000000, 2000000, 5000000, 10000000, 20000000)
ADC_RATES = (10000, 20000, 50000, 100000, 200000, 250000, 500000)


def profile(pid, product):
    if pid == 0x000c:
        return 4, 'cmsis-dap', 'RP2040 · CMSIS-DAP + UART'
    if pid == 0x000a and product == LOGIC_PRODUCT:
        return 5, 'sump8', 'LA-RP2040 · 8 通道逻辑分析仪'
    if pid == 0x000a and product == ADC_PRODUCT:
        return 7, 'adc12', 'LA-RP2040 · ADC 示波器'
    return 6, 'bootsel' if pid == 0x0003 else 'unknown', 'RP2040 · BOOTSEL' if pid == 0x0003 else 'RP2040 · 未识别固件'


def discover(ports):
    found, warnings = [], []
    try:
        import usb.core, usb.util
        for dev in usb.core.find(find_all=True, idVendor=0x2e8a):
            if dev.idProduct not in (0x0003, 0x000a, 0x000c):
                continue
            def descriptor(index):
                try:
                    return usb.util.get_string(dev, index) if index else ''
                except Exception:
                    return ''
            product, serial = descriptor(dev.iProduct), descriptor(dev.iSerialNumber)
            matches = [p for p in ports if p['vid'] == 0x2e8a and p['pid'] == dev.idProduct and serial and p['serial'] == serial]
            port = matches[0] if len(matches) == 1 else None
            # pyserial can expose a descriptor when the USB driver cannot.
            product = product or (port or {}).get('product', '')
            mode, kind, name = profile(dev.idProduct, product)
            found.append(dict(id=f'rp:{dev.bus}:{dev.address}:{dev.idProduct:04x}', name=name,
                family='rp2040', profile=kind, mode=mode, serial=serial, product=product,
                vid='2E8A', pid=f'{dev.idProduct:04X}', bcd=dev.bcdDevice,
                version=product or '固件版本待确认', port=port['path'] if port else '',
                board_match=product in (LOGIC_PRODUCT, ADC_PRODUCT, DAP_PRODUCT)))
    except Exception:
        pass  # CDC enumeration remains useful without a libusb backend.
    for port in ports:
        if port['vid'] != 0x2e8a or port['pid'] not in (0x000a, 0x000c):
            continue
        if any(d.get('port') == port['path'] or (port['serial'] and d['serial'] == port['serial']) for d in found):
            continue
        product = port.get('product') or port.get('description', '')
        mode, kind, name = profile(port['pid'], product)
        found.append(dict(id='rp:serial:'+port['path'], name=name, family='rp2040', profile=kind,
            mode=mode, serial=port['serial'] or '', product=product, vid='2E8A', pid=f"{port['pid']:04X}",
            bcd=0, version=product, port=port['path'], board_match=product in (LOGIC_PRODUCT, ADC_PRODUCT, DAP_PRODUCT)))
    return found, warnings


def validate_capture(params, analog=False):
    from .core import integer, UserError
    p = dict(params)
    rates = ADC_RATES if analog else LOGIC_RATES
    p['rate'] = integer(p.get('rate', 100000 if analog else 1000000), min(rates), max(rates), '采样率')
    if p['rate'] not in rates:
        raise UserError('请选择支持的采样率，避免时钟量化误差')
    p['samples'] = integer(p.get('samples', 4096), 4, 32768 if analog else 100000, '采样点数')
    if not analog and p['samples'] % 4:
        raise UserError('逻辑采样点数必须为 4 的倍数')
    p['timeout'] = integer(p.get('timeout', 15), 2, 60, '等待超时秒数')
    if analog:
        p['channel'] = integer(p.get('channel', 0), 0, 2, 'ADC 通道')
        try:
            p['vref'] = float(p.get('vref', 3.3))
        except (TypeError, ValueError):
            raise UserError('请输入实测 ADC 参考电压')
        if not math.isfinite(p['vref']) or not 2.5 <= p['vref'] <= 3.3:
            raise UserError('ADC 参考电压范围为 2.5–3.3 V')
        if p['timeout'] < p['samples']/p['rate']+2:
            raise UserError('超时必须大于采集时长加 2 秒')
    else:
        p['trigger'] = str(p.get('trigger', 'none'))
        if p['trigger'] not in ('none', 'rising', 'falling', 'high', 'low'):
            raise UserError('无效触发方式')
        p['trigger_channel'] = integer(p.get('trigger_channel', 0), 0, 7, '触发通道')
    return p


def read_exact(port, size, deadline, cancelled):
    from .core import UserError
    chunks = bytearray()
    while len(chunks) < size:
        if cancelled():
            raise UserError('采集已取消')
        if time.monotonic() >= deadline:
            raise UserError(f'采集超时：已接收 {len(chunks)} / {size} 字节。请检查触发信号、接线与固件。')
        part = port.read(min(size-len(chunks), 4096))
        if part:
            chunks.extend(part)
    return bytes(chunks)


def write_all(port, data):
    from .core import UserError
    if port.write(data) != len(data):
        raise UserError('USB CDC 未完整发送命令')


def sump_commands(p):
    def cmd(code, value):
        return bytes([code])+struct.pack('<I', value)
    q = p['samples']//4-1
    frames = [cmd(0x80, 100000000//p['rate']-1), cmd(0x81, q | q << 16), cmd(0x82, 0x38)]
    if p['trigger'] != 'none':
        edge = p['trigger'] in ('rising', 'falling')
        frames += [cmd(0xc0, 3 if edge else 1),
                   cmd(0xc1, {'rising':2,'falling':1,'high':1,'low':0}[p['trigger']]),
                   cmd(0xc2, 0x0c000000 | p['trigger_channel'] << 20)]
    return frames+[b'\x01']


def serial_port(path):
    from .core import UserError
    if not path:
        raise UserError('尚未识别此固件的 CDC 端口，请检查 USB 驱动并重新连接')
    import serial
    return serial.Serial(path, 115200, timeout=.1, write_timeout=2)


def capture(p, cancelled=lambda:False, log=lambda s:None, opener=serial_port):
    from .core import UserError
    with opener(p['port']) as port:
        port.reset_input_buffer()
        try:
            write_all(port, b'\x00'*5)
            write_all(port, b'\x02')
            if read_exact(port, 4, time.monotonic()+3, cancelled) != b'1ALS':
                raise UserError('SUMP 握手不匹配，请刷入本板 SUMP8 固件')
            for frame in sump_commands(p):
                write_all(port, frame)
            log(f"8 通道 · {p['rate']} Sa/s · {p['samples']} 点 · 触发 {p['trigger']}（无前触发）")
            samples = read_exact(port, p['samples'], time.monotonic()+p['timeout'], cancelled)[::-1]
            log(f'收到 {len(samples)} 个有效采样点，已还原正向时间顺序')
            return samples
        finally:
            try: port.write(b'\x00'*5)
            except Exception: pass


def adc_capture(p, cancelled=lambda:False, log=lambda s:None, opener=serial_port):
    from .core import UserError
    with opener(p['port']) as port:
        port.reset_input_buffer()
        try:
            request = lambda op: struct.pack('<4sBBHII', b'ADC1', op, p['channel'], 0, p['samples'], p['rate'])
            write_all(port, request(0))
            ident = read_exact(port, 16, time.monotonic()+3, cancelled)
            if ident != struct.pack('<4sIII', b'ADCI', 500000, 32768, 1):
                raise UserError('ADC12 固件握手不匹配，请更新本板固件')
            write_all(port, request(1))
            deadline = time.monotonic()+p['timeout']
            magic, rate, count, status = struct.unpack('<4sIII', read_exact(port, 16, deadline, cancelled))
            if magic != b'ADC1' or rate != p['rate'] or count != p['samples'] or status:
                raise UserError(f'ADC 采集头无效或硬件报告错误 ({status})')
            raw = read_exact(port, count*2, deadline, cancelled)
            values = list(struct.unpack('<'+'H'*count, raw))
            if any(v > 4095 for v in values):
                raise UserError('ADC FIFO 报告采样错误，数据未采纳')
            log(f"ADC{p['channel']} / GP{26+p['channel']} · {rate} Sa/s · {count} 点 · 12 bit 原始码")
            return raw, measurements(values, p['vref'])
        finally:
            try: port.write(b'\x18')
            except Exception: pass


def measurements(values, vref):
    volts = [v*vref/4096 for v in values]
    mean = sum(volts)/len(volts)
    return dict(min_v=min(volts), max_v=max(volts), vpp=max(volts)-min(volts), mean_v=mean,
        rms_v=math.sqrt(sum(v*v for v in volts)/len(volts)),
        clipped=sum(v in (0,4095) for v in values), reference_v=vref,
        note='按参考电压换算；未校准。12 bit 为码宽，不代表有效精度。')


def exports(samples, rate):
    rows = ['time_s,'+','.join(f'D{i}_GP{20+i}' for i in range(8))]
    rows += [f'{n/rate:.9f},'+','.join(str(v>>i&1) for i in range(8)) for n,v in enumerate(samples)]
    yield 'logic.csv', ('\n'.join(rows)+'\n').encode()
    ids = 'abcdefgh'
    vcd = ['$timescale 1 ns $end','$scope module LA_RP2040 $end']
    vcd += [f'$var wire 1 {ids[i]} D{i}_GP{20+i} $end' for i in range(8)]
    vcd += ['$upscope $end','$enddefinitions $end']
    previous = None
    for n, value in enumerate(samples):
        if value != previous:
            vcd.append(f'#{round(n*1e9/rate)}')
            vcd += [f'{value>>i&1}{ids[i]}' for i in range(8) if previous is None or (value^previous)&(1<<i)]
        previous = value
    vcd.append(f'#{round(len(samples)*1e9/rate)}')
    yield 'logic.vcd', ('\n'.join(vcd)+'\n').encode()
    archive = io.BytesIO()
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
        z.writestr('version', '2')
        meta = f'[global]\nsigrok version=0.5.2\n\n[device 1]\ncapturefile=logic-1\nunitsize=1\ntotal probes=8\nsamplerate={rate} Hz\n'
        meta += ''.join(f'probe{i+1}=D{i}_GP{20+i}\n' for i in range(8))
        z.writestr('metadata',meta); z.writestr('logic-1-1', samples)
    yield 'logic.sr', archive.getvalue()


def adc_exports(raw, p):
    values = struct.unpack('<'+'H'*(len(raw)//2), raw)
    rows = ['time_s,adc_code,voltage_v']+[f'{i/p["rate"]:.9f},{v},{v*p["vref"]/4096:.9f}' for i,v in enumerate(values)]
    yield f'adc{p["channel"]}.csv', ('\n'.join(rows)+'\n').encode()
    yield f'adc{p["channel"]}-u16le.bin', raw

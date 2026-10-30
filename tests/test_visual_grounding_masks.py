from pathlib import Path

from PIL import Image

from jevlight.vlalight_images import isolate_jinan_movements as isolate_request


def test_each_camera_view_keeps_only_its_mapped_movement_masks(tmp_path):
    views = ('NORTHBOUND', 'EASTBOUND', 'SOUTHBOUND', 'WESTBOUND')
    expected = {'NORTHBOUND': {'ST', 'SL'}, 'EASTBOUND': {'WT', 'WL'},
                'SOUTHBOUND': {'NT', 'NL'}, 'WESTBOUND': {'ET', 'EL'}}
    assets = {}
    state = {'intersection_id': 'sample', 'current_views': [],
             'previous_views': [], 'elapsed_s': 15}
    for group in ('current_views', 'previous_views'):
        for view in views:
            ref = f'{group}_{view}'
            assets[ref] = tmp_path / f'{ref}.jpg'
            Image.new('RGB', (384, 720), (120, 120, 120)).save(assets[ref])
            state[group].append({'view': view, 'image': ref})

    masked, _, paths = isolate_request(state, {}, assets, tmp_path / 'masked')

    for group in ('current_views', 'previous_views'):
        for source in masked[group]:
            assert {item['movement'] for item in masked[group]
                    if item['view'] == source['view']} == expected[source['view']]
    assert len(paths) == 16


def test_left_turn_keeps_centerline_lane_and_excludes_right_and_through(tmp_path):
    source = tmp_path / 'NORTHBOUND.png'
    pixels = Image.new('RGB', (384, 720))
    for x in range(384):
        for y in range(720):
            pixels.putpixel((x, y), (x % 256, y % 256, 100))
    pixels.save(source)
    state = {'intersection_id': 'i',
             'current_views': [{'view': 'NORTHBOUND', 'image': 'current'}],
             'previous_views': [], 'elapsed_s': None}

    masked, _, assets = isolate_request(state, {}, {'current': source}, tmp_path / 'masked')
    left = Image.open(assets['current_SL'])
    through = Image.open(assets['current_ST'])
    pixels = Image.open(source)

    assert left.getpixel((80, 400)) == (32, 32, 32)
    assert left.getpixel((120, 400)) == (32, 32, 32)
    assert left.getpixel((170, 400)) == pixels.getpixel((170, 400))
    assert through.getpixel((80, 400)) == (32, 32, 32)
    assert through.getpixel((120, 400)) == pixels.getpixel((120, 400))
    assert through.getpixel((170, 400)) == (32, 32, 32)


def test_all_static_jinan_signal_connections_define_right_through_left_in_lane_order():
    import xml.etree.ElementTree as ET
    from collections import defaultdict
    root = Path(__file__).resolve().parents[1]
    network = ET.parse(root / 'data/Jinan/3_4/roadnet_3_4.net.xml').getroot()
    connections = defaultdict(lambda: defaultdict(set))
    for connection in network.findall('connection'):
        if connection.get('tl'):
            key = (connection.get('tl'), connection.get('from'))
            connections[key][int(connection.get('fromLane'))].add(connection.get('dir'))
    assert len(connections) == 48
    assert all(dict(lanes) == {0: {'r'}, 1: {'s'}, 2: {'l'}} for lanes in connections.values())
    edges = {edge.get('id'): edge for edge in network.findall('edge')}
    for _, edge_id in connections:
        lanes = sorted(edges[edge_id].findall('lane'), key=lambda lane: int(lane.get('index')))
        shapes = [[tuple(map(float, point.split(','))) for point in lane.get('shape').split()]
                  for lane in lanes]
        dx, dy = (shapes[0][-1][axis] - shapes[0][0][axis] for axis in (0, 1))
        # The camera faces approaching vehicles: their left is image-right.
        lateral = [-dy * shape[-1][0] + dx * shape[-1][1] for shape in shapes]
        assert lateral[0] < lateral[1] < lateral[2]

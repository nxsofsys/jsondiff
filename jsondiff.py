'''
The MIT License (MIT)

Copyright (c) 2014 Ilya Volkov

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
'''

from collections import MutableMapping, MutableSequence
from collections import namedtuple, defaultdict
import itertools

_compare_info = namedtuple('_compare_info', 'ops removed added')
_op_add = namedtuple('_op_add', 'path key value')
_op_remove = namedtuple('_op_remove', 'path key')
_op_replace = namedtuple('_op_replace', 'path value')
_op_move = namedtuple('_op_move', 'oldpath oldkey path key')

def _freeze(item):
    if isinstance(item, MutableMapping):
        result = frozenset(((key, _freeze(value)) for key, value in item.iteritems()))
        return result
    elif isinstance(item, MutableSequence):
        result = frozenset((_freeze(value) for value in item))
        return result
    else:
        return item

def _path_join(path, key):
    return path + '/' + unicode(key).replace('~', '~0').replace('/', '~1')

def _print_op(op):
    if not op:
        return
    if type(op) == _op_add:
        print {'op': 'add', 'path': _path_join(op.path, op.key), 'value': op.value}
    elif type(op) == _op_remove:
        print {'op': 'remove', 'path': _path_join(op.path, op.key)}
    elif type(op) == _op_replace:
        print {'op': 'replace', 'path': op.path, 'value': op.value}
    elif type(op) == _op_move:
        print {'op': 'move', 'path': _path_join(op.path, op.key), 'from': _path_join(op.oldpath, op.oldkey)}

def _restore_op(info, index):
        op = info.ops[index]
        key = op.key
        if isinstance(key, basestring):
            return op
        for i in xrange(index+1, len(info.ops)):
            his = info.ops[i]
            if his == None:
                continue
            if type(his) == _op_move:
                if his.oldpath == op.path:
                    if his.oldkey < key:
                        key -= 1
                    else:
                        if type(op) == _op_add:
                            his = info.ops[i] = his._replace(
                                oldkey = his.oldkey - 1)
                        elif type(op) == _op_remove:
                            his = info.ops[i] = his._replace(
                                oldkey = his.oldkey + 1) 
                if his.path == op.path:
                    if his.key <= key:
                        key += 1
                    else:
                        if type(op) == _op_add:
                            his = info.ops[i] = his._replace(
                                key = his.key - 1)
                        elif type(op) == _op_remove:
                            his = info.ops[i] = his._replace(
                                key = his.key + 1)
            if type(his) == _op_remove:
                if his.path == op.path and his.key < key:
                    key -= 1
            if type(his) == _op_add:
                if his.path == op.path and his.key <= key:
                    key += 1
        return op._replace(key = key)

def _item_added(path, key, info, item):
    frozen = _freeze(item)
    if frozen in info.removed:
        index = info.removed[frozen].pop(0)
        if not info.removed[frozen]:
            del info.removed[frozen]
        
        op = _restore_op(info, index)
        info.ops[index] = None
        info.ops.append(_op_move(op.path, op.key, path, key))
    else:
        info.added[frozen].append(len(info.ops))
        info.ops.append(_op_add(path ,key, item))

def _item_removed(path, key, info, item):
    frozen = _freeze(item)
    if frozen in info.added:
        index = info.added[frozen].pop(0)
        if not info.added[frozen]:
            del info.added[frozen]
        op = _restore_op(info, index)
        info.ops[index] = None
        info.ops.append(_op_move(path, key, op.path, op.key-1 if op.key > 0 else op.key))
    else:
        info.removed[frozen].append(len(info.ops))
        info.ops.append(_op_remove(path, key))

def _item_replaced(path, info, item):
    info.ops.append(_op_replace(path, item))

def _compare_dicts(path, info, src, dst):
    added_keys = dst.viewkeys() - src.viewkeys()
    removed_keys = src.viewkeys() - dst.viewkeys()
    for key in added_keys:
        _item_added(path, str(key), info, dst[key])
    for key in removed_keys:
        _item_removed(path, str(key), info, src[key])
    for key in src.viewkeys() & dst.viewkeys():
        _compare_values(_path_join(path, key), info, src[key], dst[key])

def _compare_lists(path, info, src, dst):
    key = max(len(src), len(dst))
    values = list(itertools.izip_longest(src, dst))
    for key in xrange(key-1, -1, -1):
        old, new = values[key]
        # if old != None and new != None:
        #     _compare_values(_path_join(path, key), info, old, new)
        if old != None:
            _item_removed(path, key, info, old)
        if new != None:
            _item_added(path, key, info, new)

def _compare_values(path, info, src, dst):
    if src == dst:
        return
    elif isinstance(src, MutableMapping) and \
            isinstance(dst, MutableMapping):
        _compare_dicts(path, info, src, dst)
    elif isinstance(src, MutableSequence) and \
            isinstance(dst, MutableSequence):
        _compare_lists(path, info, src, dst)
    else:
        _item_replaced(path, info, dst)

def _execute(info):
    for op in info.ops:
        if not op:
            continue
        if type(op) == _op_add:
            yield {'op': 'add', 'path': _path_join(op.path, op.key), 'value': op.value}
        elif type(op) == _op_remove:
            yield {'op': 'remove', 'path': _path_join(op.path, op.key)}
        elif type(op) == _op_replace:
            yield {'op': 'replace', 'path': op.path, 'value': op.value}
        elif type(op) == _op_move:
            yield {'op': 'move', 'path': _path_join(op.path, op.key), 'from': _path_join(op.oldpath, op.oldkey)}

def make(src, dst, **kwargs):
    result = []
    info = _compare_info([], defaultdict(list), defaultdict(list))
    path = ''
    _compare_values(path, info, src, dst)
    return [v for v in _execute(info)]

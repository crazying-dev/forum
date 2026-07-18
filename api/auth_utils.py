import random
import hashlib
import sys
from api.config import (
    AUTH_SALT,
    AUTH_NUM_REPLACEMENTS,
    AUTH_LETTER_VERSIONS,
    AUTH_SYMBOL_VERSIONS,
    AUTH_COMBINING_SETS,
    AUTH_ZW_SETS,
    AUTH_PADDING_SETS,
    AUTH_LIST_FOR_1,
)

sys.set_int_max_str_digits(10000)

_SALT_HASH = hashlib.sha256(AUTH_SALT.encode("utf-8")).hexdigest()


def _char_ord(s):
    end = 0
    try:
        s = str(s)
        for i in s:
            end += ord(i)
    except Exception:
        end = s
    return end


def _str_hash(s):
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _get_random_str(s, length):
    result = ""
    for i in range(length):
        result = result + random.choice(s)
    return result


def _salt_for_int():
    a = 0
    for i in _SALT_HASH:
        a += _char_ord(_str_hash(i))
    return a


def _bytes_hash(s):
    s = str(s)
    return hashlib.sha256(s.encode("utf-8")).digest()


def _get_single_char():
    selected_group = random.choice([AUTH_PADDING_SETS, AUTH_ZW_SETS, AUTH_COMBINING_SETS])
    sub = random.choice(selected_group)
    if isinstance(sub, list):
        return random.choice(sub)
    else:
        return random.choice(sub)


def _process_char(input_data):
    salt_int = _salt_for_int()
    for i in input_data:
        ord_val = _char_ord(i)
        random.seed(_bytes_hash(f"{salt_int * ord_val}--_--{salt_int}---__----{ord_val}"))
        for _i in AUTH_NUM_REPLACEMENTS:
            input_data = input_data.replace(_i, random.choice(AUTH_NUM_REPLACEMENTS[_i]))
        __list = random.choice(AUTH_LETTER_VERSIONS)
        for _i in __list:
            input_data = input_data.replace(_i, random.choice(__list[_i]))
        __list = random.choice(AUTH_SYMBOL_VERSIONS)
        for _i in __list:
            input_data = input_data.replace(_i, random.choice(__list[_i]))

    prefix = _get_single_char()
    suffix = _get_single_char()

    end = prefix + input_data + suffix
    endnum = []
    for i in end:
        endnum.append(_char_ord(i))
    return endnum


def generate_auth_token(data):
    end = ""
    for i in str(data):
        for _i in _process_char(i):
            end = end + str(_i)
    _end = int(end)
    salt_int = _salt_for_int()
    random.seed(_bytes_hash(f'{salt_int}-==-{_SALT_HASH}==1==-=-{salt_int * _end}==--=-={_end}'))
    __end = ""
    __end = _get_random_str(end, 20)
    __end = _get_random_str(_str_hash(__end), 10)
    return __end


def verify_auth_token(data, token):
    if not data or not token:
        return False
    expected = generate_auth_token(data)[:10]
    if token[:10] == expected:
        return True
    return False

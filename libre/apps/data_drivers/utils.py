from __future__ import absolute_import

import csv
from HTMLParser import HTMLParser
import logging

from dateutil.parser import parse
import pyparsing
from shapely import geometry

from .literals import (DATA_TYPE_DATE, DATA_TYPE_DATETIME, DATA_TYPE_NUMBER, DATA_TYPE_STRING,
    DATA_TYPE_TIME, THOUSAND_SYMBOL, DECIMAL_SYMBOL)
from .exceptions import Http400

logger = logging.getLogger(__name__)

enclosed_parser = pyparsing.Forward()
nestedBrackets = pyparsing.nestedExpr('[', ']', content=enclosed_parser)
enclosed_parser << (pyparsing.Word(pyparsing.alphanums + '-' + '.' + '(' + ')') | ',' | nestedBrackets)

DATA_TYPE_FUNCTIONS = {
    DATA_TYPE_STRING: lambda x: unicode(x).strip(),
    DATA_TYPE_NUMBER: lambda x: convert_to_number(x),
    DATA_TYPE_DATETIME: lambda x: parse(x),
    DATA_TYPE_DATE: lambda x: parse(x).date(),
    DATA_TYPE_TIME: lambda x: parse(x).time(),
}


def parse_enclosed(string):
    return enclosed_parser.parseString(string).asList()


# http://stackoverflow.com/questions/4248399/page-range-for-printing-algorithm
def parse_range(astr):
    result = set()
    for part in astr.split(u','):
        x = part.split(u'-')
        result.update(range(int(x[0]), int(x[-1]) + 1))
    return sorted(result)


def convert_to_number(data):
    # Get rid of dollar signs and thousand separators
    data = data.replace(THOUSAND_SYMBOL, '').replace('$', '')

    if '(' and ')' in data:
        # Is a negative number
        return -convert_to_number(data.replace(')', '').replace('(', ''))
    else:
        if DECIMAL_SYMBOL in data:
            # It is a decimal number
            return float(data)
        else:
            # Otherwise it is an integer
            return int(data)


class UnicodeReader:
    """
    A CSV reader which will iterate over lines in the CSV file "f",
    which is encoded in the given encoding.
    """

    def __init__(self, f, dialect=csv.excel, encoding='utf-8', **kwds):
        self.reader = csv.reader(f, dialect=dialect, **kwds)
    def next(self):
        row = self.reader.next()
        if row:
            try:
                return [unicode(s, 'utf-8') for s in row]
            except UnicodeDecodeError:
                try:
                    return [s.decode('iso-8859-1') for s in row]
                except UnicodeDecodeError:
                    return []
        else:
            return []

    def __iter__(self):
        return self


def parse_value(string):
    from .models import Source

    html_parser = HTMLParser()
    string = html_parser.unescape(string)

    logger.debug('parsing: %s' % string)
    if string[0] == '"' and string[-1] == '"':
        # Strip quotes
        return unicode(string[1:-1])
    elif string.startswith('Point'):
        # Is a point geometry data type
        x, y = string.strip().replace('Point(', '').replace(')', '').split(',')

        # Check if the Point data type is also specifing a buffer
        buffer_size = None
        if '.buffer(' in y:
            y, buffer_size = y.split('.buffer(')

        value = geometry.Point(float(x), float(y))

        if buffer_size:
            value = value.buffer(float(buffer_size[:-1]))

        return value
    elif string.startswith('LineStrings'):
        # Is a point geometry data type
        points = string.strip().replace('LineStrings(', '').replace(')', '')

        value = geometry.LineStrings(parse_value(points))

        return value
    elif string.startswith('LinearRings'):
        # Is a point geometry data type
        points = string.strip().replace('LinearRings(', '').replace(')', '')

        value = geometry.LinearRings(parse_value(points))

        return value
    elif string.startswith('Polygon'):
        # Is a point geometry data type
        points = string.strip().replace('Polygon(', '').replace(')', '')

        value = geometry.Polygon(parse_value(points))

        return value
    elif string.startswith('MultiPoint'):
        # Is a point geometry data type
        points = string.strip().replace('MultiPoint(', '').replace(')', '')

        value = geometry.MultiPoint(parse_value(points))

        return value
    elif string.startswith('MultiLineString'):
        # Is a point geometry data type
        points = string.strip().replace('MultiLineString(', '').replace(')', '')

        value = geometry.MultiLineString(parse_value(points))

        return value
    elif string.startswith('MultiPolygon'):
        # Is a point geometry data type
        points = string.strip().replace('MultiPolygon(', '').replace(')', '')

        value = geometry.MultiPolygon(parse_value(points))

        return value
    elif string.startswith('Geometry'):
        # Is a point geometry data type
        points = string.strip().replace('Geometry(', '').replace(')', '')

        # Check if the geometry data type is also specifing a buffer
        buffer_size = None
        if '.buffer(' in points:
            points, buffer_size = points.split('.buffer(')

        value = geometry.shape(parse_value(points))

        if buffer_size:
            value = value.buffer(float(buffer_size[:-1]))

        return value
    elif string[0] == '[' and string[-1] == ']':
        # Is a list of values
        logger.debug('Is a list')

        result = []

        for string in parse_enclosed(string)[0]:
            if string != ',':  # Single comma, don't process
                if ',' in string:
                    # is a nested list, recompose
                    result.append(parse_value('[%s]' % (''.join(string))))
                else:
                    # is a single element, parse as is
                    result.append(parse_value(string))

        return list(result)
    elif string.startswith('DateTime'):
        # Is a datetime
        logger.debug('Is a datetime')
        date_string = string.replace('DateTime(', '').replace(')', '')
        return parse(date_string)
    elif string.startswith('Date'):
        # Is a date
        logger.debug('Is a date')
        date_string = string.replace('Date(', '').replace(')', '')
        return parse(date_string).date()
    elif string.startswith('Time'):
        # Is a time
        logger.debug('Is a time')
        date_string = string.replace('Time(', '').replace(')', '')
        return parse(date_string).time()
    else:
        # Check for reference
        parts = string.split('.')
        source_slug = parts[0]

        try:
            new_source = Source.objects.get_subclass(slug=source_slug)
        except Source.DoesNotExist:
            logger.debug('no source named: %s' % source_slug)
            logger.debug('Is a number')
            try:
                return convert_to_number(string)
            except ValueError:
                raise Http400('Invalid value or unknown source: %s' % string)
        else:
            logger.debug('got new source named: %s' % source_slug)
            # Rebuild the parameters for this enclosed value
            new_string = u'.'.join(parts[1:])
            parameters = {}
            for part in new_string.split('&'):
                key, value = part.split('=')
                parameters[key] = value

            return new_source.get_all(parameters=parameters)

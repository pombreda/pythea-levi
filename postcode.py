import re

class Zip():

    lowermask = '0000AA'
    highermask = '9999ZZ'

    def __init__(self, range):
        if len(range) < 2:
            range.append(range[0])
        # FIXME: expand the range for upper and lower bounds
        self.low = self.expandlower(range[0])
        self.high = self.expandhigher(range[1])

    def check(self, zipcode):
        return self.low <= zipcode <= self.high

    def expandlower(self, partial):
        return partial + Zip.lowermask[len(partial):]

    def expandhigher(self, partial):
        return partial + Zip.highermask[len(partial):]

def parse(s):
    codes = s.split(',')
    for code in codes:
        code = code.replace(' ', '')
        range = code.split('-')
        z = Zip(range)
        print z.low, z.high
        print z.check('1230XY')
        


if __name__ == '__main__':
    import sys
    parse(sys.argv[1])
    
    

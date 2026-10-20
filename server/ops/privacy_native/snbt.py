"""Bounded SNBT inspection for Ledger's textual block/entity/item history.
Unknown syntax or opaque byte arrays require native/case review, not an absence claim.
"""
import re
from .identity_codec import IntArray,LongArray,LIMIT

class Parser:
    def __init__(self,text):
        if len(text.encode())>LIMIT:raise ValueError('SNBT exceeds budget')
        self.text=text;self.pos=0;self.nodes=0
    def ws(self):
        while self.pos<len(self.text) and self.text[self.pos].isspace():self.pos+=1
    def peek(self):self.ws();return self.text[self.pos:self.pos+1]
    def expect(self,char):
        if self.peek()!=char:raise ValueError('Unsupported/truncated SNBT')
        self.pos+=1
    def word(self):
        self.ws();match=re.match(r'[A-Za-z0-9_.+\-]+',self.text[self.pos:])
        if not match:raise ValueError('Unsupported SNBT token')
        self.pos+=len(match[0]);return match[0]
    def quoted(self):
        quote=self.peek();self.pos+=1;result=''
        while self.pos<len(self.text):
            char=self.text[self.pos];self.pos+=1
            if char==quote:return result.encode('utf-16-le',errors='surrogatepass').decode('utf-16-le')
            if char=='\\':
                if self.pos>=len(self.text):raise ValueError('Truncated SNBT escape')
                char=self.text[self.pos];self.pos+=1
                if char=='u':
                    raw=self.text[self.pos:self.pos+4]
                    if len(raw)!=4 or not re.fullmatch('[0-9a-fA-F]{4}',raw):raise ValueError('Invalid SNBT Unicode')
                    result+=chr(int(raw,16));self.pos+=4;continue
                if char in '\\\"\'':result+=char;continue
                if char not in 'nrtbf':raise ValueError('Unknown SNBT escape')
                result+={'n':'\n','r':'\r','t':'\t','b':'\b','f':'\f'}[char]
            else:result+=char
        raise ValueError('Unclosed SNBT string')
    def value(self,depth=0):
        self.nodes+=1
        if depth>64 or self.nodes>500000:raise ValueError('SNBT nesting budget')
        char=self.peek()
        if char in ('"',"'"):return self.quoted()
        if char=='{':
            self.pos+=1;result={}
            if self.peek()=='}':self.pos+=1;return result
            while True:
                key=self.quoted() if self.peek() in ('"',"'") else self.word();self.expect(':')
                if key in result:raise ValueError('Duplicate SNBT field')
                result[key]=self.value(depth+1)
                if self.peek()=='}':self.pos+=1;return result
                self.expect(',')
        if char=='[':
            self.pos+=1;kind=None
            if self.peek() in ('B','I','L') and self.text[self.pos+1:self.pos+2]==';':kind=self.peek();self.pos+=2
            values=[]
            if self.peek()!=']':
                while True:
                    values.append(self.value(depth+1))
                    if self.peek()==']':break
                    self.expect(',')
            self.expect(']')
            if kind and any(type(value) is not int for value in values):raise ValueError('Invalid SNBT typed array')
            if kind=='B' and values:raise ValueError('Opaque SNBT byte array needs review')
            return IntArray(values) if kind=='I' else LongArray(values) if kind=='L' else values
        token=self.word()
        if token in ('true','false'):return token=='true'
        if re.fullmatch(r'[-+]?\d+[bBsSlL]?',token):return int(token[:-1] if token[-1].isalpha() else token)
        if re.fullmatch(r'[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?[fFdD]?',token):return float(token[:-1] if token[-1] in 'fFdD' else token)
        return token

def decode(text):
    parser=Parser(text);result=parser.value();parser.ws()
    if parser.pos!=len(text):raise ValueError('Trailing/unknown SNBT syntax')
    return result

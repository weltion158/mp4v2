#!/usr/bin/env python3
#

import io
import re
import sys
import time
import xml.parsers.expat

from optparse import OptionParser

###############################################################################

writer = None

###############################################################################

class StreamEntry:
    def __init__( self, object, isElement ):
        self.object    = object
        self.isElement = isElement
    
###############################################################################

class Element:
    def __init__( self, parent, text=True, strip=True, delimBegin=None, delimEnd=None, newline=0 ):
        self._parent     = parent
        self._text       = text
        self._strip      = strip
        self._delimBegin = delimBegin
        self._delimEnd   = delimEnd
        self._newline    = newline
        self._stream     = []

    def _addElement( self, child ):
        self._stream.append( StreamEntry( child, True ))

    def _addText( self, text ):
        if self._text:
            self._stream.append( StreamEntry( text, False ))

    def _write( self, file ):
        if self._delimBegin:
            file.write( self._delimBegin )
        for entry in self._stream:
            if entry.isElement:
                entry.object.write( file )
            else:
                file.write( str(entry.object) )
        if self._delimEnd:
            file.write( self._delimEnd )

    def write( self, file ):
        if self._newline > writer.newlineCount:
            file.write( '\n' * (self._newline - writer.newlineCount))
        self._write( file )

###############################################################################

class Document( Element ):
    def __init__( self ):
        Element.__init__( self, None )
        self._stack        = [ self ]
        self._pending      = self
        self._summary      = None
        self._debugIndent  = ''
        self._chapterLevel = 0
        self._sectionLevel = 0
        self._dividerCount = 0

        self._pragmaSummary = PragmaElement( self, 'summary' )
        self._pragmaLabels = PragmaElement( self, 'labels' )
        self._pragmaLabels._addText( 'xml2wiki,Distribution,Featured' )

    def _pop( self ):
        self._stack.pop()
        self._pending = self._stack[-1]
        return self._pending

    def _pushChild( self, child, add=True ):
        if add:
            self._pending._addElement( child );
        self._stack.append( child )
        self._pending = child
        return self._pending

    def _chapterBegin( self ):
        self._chapterLevel = self._chapterLevel + 1

    def _chapterEnd( self ):
        self._chapterLevel = self._chapterLevel - 1

    def _sectionBegin( self ):
        self._sectionLevel = self._sectionLevel + 1

    def _sectionEnd( self ):
        self._sectionLevel = self._sectionLevel - 1

    def _write( self, file ):
        self._pragmaSummary.write( file )
        file.write( '\n' )
        self._pragmaLabels.write( file )
        if options.date:
            file.write( "\n\n  ===== `[`generated by xml2wiki on %s`]` =====" % (time.strftime( '%c' ) ))
        if options.toc:
            file.write( '\n\n<wiki:toc max_depth="3" />' )
        Element._write( self, file )
        file.write( '\n' )

    def handleElementBegin( self, name, attrs ):
        self._debugIndent = '    ' * (len(self._stack) - 1)
        if options.verbose:
            print( '%sBEGIN %s %s' % (self._debugIndent, name, attrs))

        e = None
        shouldAdd = True

        if name == 'b':
            # we prefix with italiac delims in case this is on indented line
            # which gets confifused by google's wiki to mean bullet item
            e = Element( self._pending, delimBegin='__*', delimEnd='*' )
        elif name == 'chapter':
            self._chapterBegin()
        elif name == 'code':
            e = Element( self._pending, delimBegin='`', delimEnd='`' )
        elif name == 'command':
            e = Element( self._pending, delimBegin='`', delimEnd='`' )
        elif name == 'enumerate':
            e = EnumerateElement( self._pending )
        elif name == 'example':
            e = CodeElement( self._pending )
        elif name == 'file':
            e = Element( self._pending, delimBegin='`', delimEnd='`' )
        elif name == 'i':
            e = Element( self._pending, delimBegin='_', delimEnd='_' )
        elif name == 'itemize':
            e = ItemizeElement( self._pending )
        elif name == 'item':
            e = ItemElement( self._pending )
        elif name == 'majorheading':
            e = self._pragmaSummary
            shouldAdd = False
        elif name == 'para':
            e = ParagraphElement( self._pending )
        elif name == 'quotation':
            e = IndentedElement( self._pending )
        elif name == 'samp':
            e = Element( self._pending, delimBegin='`', delimEnd='`' )
        elif name == 'section' or name == 'subsection':
            self._sectionBegin()
        elif name == 'table':
            e = Element( self._pending, newline=1, delimBegin='<table border="1" cellpadding="4">', delimEnd='</table>', strip=True )
        elif name == 'tableitem':
            e = TableItemElement( self._pending )
        elif name == 'tableterm':
            e = Element( self._pending, delimBegin='<td width="15%">', delimEnd='</td>' )
        elif name == 'title':
            e = HeadingElement( self._pending, self._chapterLevel + self._sectionLevel )
        elif name == 'unnumbered' or name == 'unnumberedsec':
            self._chapterBegin()
        elif name == 'uref':
            e = UrefInline( self._pending )
        elif name == 'urefdesc':
            e = UrefDescInline( self._pending )
        elif name == 'urefurl':
            e = UrefUrlInline( self._pending )
        elif name == 'xref':
            e = XrefInline( self._pending )
        elif name == 'xrefnodename':
            e = XrefNodenameInline( self._pending )

        if not e:
            self._pushChild( UnknownElement( self._pending ) )
            if options.verbose > 2:
                print( 'UNKNOWN:', name )
        else:
            self._pushChild( e, add=shouldAdd )

    def handleElementEnd( self, name ):
        if name == 'chapter':
            self._chapterEnd()
        elif name == 'section' or name == 'subsection':
            self._sectionEnd()
        elif name == 'unnumbered' or name == 'unnumberedsec':
            self._sectionEnd()

        self._pop()
        self._debugIndent = '    ' * (len(self._stack) - 1)
        if options.verbose:
            print( '%sEND %s' % (self._debugIndent, name))

    def handleCharacterData( self, data ):
        if options.verbose > 1:
            print( '%s[%s]' % (self._debugIndent, data.strip()))
        self._pending._addText( data )

###############################################################################

class UnknownElement( Element ):
    def __init__( self, parent ):
        Element.__init__( self, parent, text=False )

###############################################################################

class PragmaElement( Element ):
    def __init__( self, parent, keyword ):
        Element.__init__( self, parent, delimBegin=('#' + keyword + ' ') )

###############################################################################

class BlockElement( Element ):
    def __init__( self, parent ):
        Element.__init__( self, parent, newline=2, text=False )

###############################################################################

class CodeElement( Element ):
    def __init__( self, parent ):
        Element.__init__( self, parent, newline=2, delimBegin='{{{\n', delimEnd='\n}}}\n' )

###############################################################################

class HeadingElement( Element ):
    def __init__( self, parent, level ):
        Element.__init__( self, parent, newline=2 )
        self._delimBegin = ('=' * level) + ' '
        self._delimEnd   = ' ' + ('=' * level) + '\n'

        # insert divider for level 1 headers
        if level == 1:
            if options.toc or doc._dividerCount:
                self._delimBegin = '----\n%s' % (self._delimBegin)
            doc._dividerCount = doc._dividerCount + 1

###############################################################################

class IndentedElement( BlockElement ):
    def _write( self, file ):
        writer.increase()
        Element._write( self, file )
        writer.decrease()

###############################################################################

class EnumerateElement( IndentedElement ):
    pass

###############################################################################

class ItemizeElement( IndentedElement ):
    pass

###############################################################################

class ItemElement( BlockElement ):
    def __init__( self, parent ):
        BlockElement.__init__( self, parent )
        self._newline = 1
        if isinstance( parent, TableItemElement ):
            self._newline    = 0
            self._delimBegin = '<td>'
            self._delimEnd   = '</td>'

###############################################################################

class ParagraphElement( Element ):
    def __init__( self, parent ):
        Element.__init__( self, parent, newline=2 )
        if isinstance( parent, ItemElement ):
            if isinstance( parent._parent, TableItemElement ):
                self._newline = 0
            elif isinstance( parent._parent, EnumerateElement ):
                self._newline    = 1
                self._delimBegin = '# '
            else:
                self._newline    = 1
                self._delimBegin = '* '

###############################################################################

class TableItemElement( Element ):
    def __init__( self, parent ):
        Element.__init__( self, parent, newline=1, text=False )
        self._delimBegin = '<tr>'
        self._delimEnd   = '</tr>'

###############################################################################

class UrefInline( Element ):
    def __init__( self, parent ):
        Element.__init__( self, parent, text=False, delimBegin='[', delimEnd=']' )

###############################################################################

class UrefDescInline( Element ):
    def __init__( self, parent ):
        Element.__init__( self, parent, delimBegin=' ' )

###############################################################################

class UrefUrlInline( Element ):
    def __init__( self, parent ):
        Element.__init__( self, parent )

###############################################################################

class XrefInline( Element ):
    def __init__( self, parent ):
        Element.__init__( self, parent, text=False )

###############################################################################

class XrefNodenameInline( Element ):
    def __init__( self, parent ):
        Element.__init__( self, parent )

    def _write( self, file ):
        buffer = io.StringIO()
        Element._write( self, buffer )
        name = str( buffer.getvalue() )
        anchor = re.sub( ' ', '_', name )
        file.write( '[#%s %s]' % (anchor, name) )

###############################################################################

class IndentedWriter:
    def __init__( self, size, file ):
        self._chunk   = ' ' * size
        self._file    = file
        self._level   = 0
        self._indent  = ''
        self._pending = False

        self.newlineCount = 0

    def decrease( self ):
        self._level  = self._level - 1
        self._indent = self._chunk * self._level

    def increase( self ):
        self._level  = self._level + 1
        self._indent = self._chunk * self._level

    def write( self, data ):
        for b in data:
            if self._pending:
                self._pending = False
                self._file.write( self._indent )
            if b == '\n':
                self.newlineCount = self.newlineCount + 1
                self._pending = True
            else:
                self.newlineCount = 0
            self._file.write( b )

###############################################################################

parser = OptionParser( 'Usage: %prog [OPTIONS] xml' )
parser.add_option( '-d', '--date', action='store_true', default=False, help='generate date-stamp under title' )
parser.add_option( '-t', '--toc', action='store_true', default=False, help='generate table of contents' )
parser.add_option( '-v', '--verbose', action='count', default=False, help='increase verbosity' )

(options, args) = parser.parse_args()

if( len(args) != 1 ):
    parser.error( 'incorrect number of arguments' )

###############################################################################

doc = Document()
xml = xml.parsers.expat.ParserCreate()

xml.StartElementHandler  = doc.handleElementBegin
xml.EndElementHandler    = doc.handleElementEnd
xml.CharacterDataHandler = doc.handleCharacterData

with open( args[0], 'rb' ) as fin:
    xml.ParseFile( fin )

writer = IndentedWriter( 4, sys.stdout )
doc.write( writer )

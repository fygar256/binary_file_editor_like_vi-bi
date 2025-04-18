#!/usr/bin/python3
import sys
import tty
import termios
import string
import copy
import re
import os
import argparse
ESC='\033['
LENONSCR=(20*16)
BOTTOMLN=23
UNKNOWN=0xffffffffffffffffffffffffffffffff
mem=[]
yank=[]
coltab=[0,1,4,5,2,6,3,7]
filename=""
lastchange=False
modified=False
newfile=False
homeaddr=0
insmod=False
curx=0
cury=0
mark=[UNKNOWN] * 26
smem=[]
regexp=False
remem=''
span=0
nff=True
verbose=False
scriptingflag=False
stack=[]

def escup(n=1):
    print(f"{ESC}{n}A",end='')

def escdown(n=1):
    print(f"{ESC}{n}B",end='')

def escright(n=1):
    print(f"{ESC}{n}C",end='')

def escleft(n=1):
    print(f"{ESC}{n}D",end='',flush=True)

def esclocate(x=0,y=0):
    print(f"{ESC}{y+1};{x+1}H",end='',flush=True)

def escscrollup(n=1):
    print(f"{ESC}{n}S",end='')

def escscrolldown(n=1):
    print(f"{ESC}{n}T",end='')

def escclear():
    print(f"{ESC}2J",end='',flush=True)
    esclocate()

def esccolor(col1=7,col2=0):
    print(f"{ESC}3{coltab[col1]}m{ESC}4{coltab[col2]}m",end='',flush=True)

def escresetcolor():
    print(f"{ESC}0m",end='')

def getch():
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    tty.setraw(sys.stdin.fileno())
    ch = sys.stdin.read(1)
    termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
    return ch

def putch(c):
    print(c,end='',flush=True)

def getln():
    s = ""
    while True:
        ch = getch()
        if ch == '\033':
            return ''
        elif ch == chr(13):
            return s
        elif ch == chr(0x7f):
            if s != '':
                escleft()
                putch(' ')
                escleft()
                s = s[:len(s) - 1]
        else:
            putch(ch)
            s += ch
    return s

def skipspc(s,idx):
    while idx<len(s):
        if s[idx]==' ':
            idx+=1
        else:
            break
    return idx

def print_title():
    global filename,modified,insmod,mem
    esclocate(0,0)
    esccolor(6)
    print(f"bi version 3.0.3 by T.Maekawa                                         {"insert   " if insmod else "overwrite"} ")
    esccolor(5)
    print(f"file:[{filename:<35}] length:{len(mem)} bytes [{("not " if not modified else "")+"modified"}]    ")

def repaint():
    print_title()
    esclocate(0,2)
    esccolor(4)
    print("OFFSET       +0 +1 +2 +3 +4 +5 +6 +7 +8 +9 +A +B +C +D +E +F 0123456789ABCDEF  ")
    esccolor(7)
    addr=homeaddr
    for y in range(0x14):
        esccolor(5)
        print(f"{(addr+y*16)&0xffffffffffff:012X} ",end='')
        esccolor(7)
        for i in range(16):
            a=y*16+i+addr
            print(f"~~ " if a>=len(mem) else f"{mem[a]:02X} ",end='')
        esccolor(6)
        for i in range(16):
            a=y*16+i+addr
            print("~" if a>=len(mem) else (chr(mem[a]) if 0x20<=mem[a]<=0x7f else "."),end='')
        print("")
    esccolor(0)

def insmem(start,mem2):
    global mem,lastchange,modified
    if start>=len(mem):
        for i in range(start-len(mem)):
            mem+=[0]
        mem=mem+mem2
        modified=True
        lastchange=True
        return

    mem1=[]
    mem3=[]
    for j in range(start):
        mem1+=[mem[j]]
    for j in range(len(mem)-start):
        mem3+=[mem[start+j]]
    mem=mem1+mem2+mem3
    modified=True
    lastchange=True

def delmem(start,end,yf):
    global yank,mem,modified,lastchange
    length=end-start+1
    if length<=0 or start>=len(mem):
        stdmm("Invalid range.")
        return
    if yf:
        yankmem(start,end)

    mem1=[]
    mem2=[]
    for j in range(start):
        mem1+=[mem[j]]
    for j in range(end+1,len(mem)):
        mem2+=[mem[j]]
    mem=mem1+mem2
    lastchange=True
    modified=True

def yankmem(start,end):
    global yank,mem
    length=end-start+1
    if length<=0 or start>=len(mem):
        stdmm("Invalid range.")
        return
    yank=[]
    cnt=0
    for j in range(start,end+1):
        if j<len(mem):
            cnt+=1
            yank+=[mem[j]]

    stdmm(f"{cnt} bytes yanked.")

def ovwmem(start,mem0):
    global mem,modified,lastchange

    if mem0==[]:
        return

    if start+len(mem0)>=len(mem):
        for j in range(start+len(mem0)-len(mem)):
            mem+=[0]

    for j in range(len(mem0)):
        if j>=len(mem):
            mem+=[mem0[j]]
        else:
            mem[start+j]=mem0[j]
    lastchange=True
    modified=True

def redmem(start,end):
    global mem
    m=[]
    for i in range(start,end+1):
        if len(mem)>i:
            m+=[mem[i]]
        else:
            m+=[0]
    return m

def cpymem(start,end,dest):
    m=redmem(start,end)
    ovwmem(dest,m)

def movmem(start,end,dest):
    global mem
    m=redmem(start,end)
    if start<=dest<=end:
        return
    l=len(mem)
    delmem(start,end,True)
    if dest>l:
        ovwmem(dest,m)
    else:
        if dest>start:
            insmem(dest-(end-start+1),m)
        else:
            insmem(dest,m)

def scrup():
    global homeaddr
    if homeaddr>=16:
        homeaddr-=16

def scrdown():
    global homeaddr
    homeaddr+=16

def fpos():
    global homeaddr,curx,cury
    return(homeaddr+curx//2+cury*16)

def inccurx():
    global curx,cury
    if curx<31:
        curx+=1
    else:
        curx=0
        if cury<19:
            cury+=1
        else:
            scrdown()

def readmem(addr):
    global mem
    if addr>=len(mem):
        return 0
    return mem[addr]

def setmem(addr,data):
    global mem,modified,lastchange
    data&=0xff
    if addr>=len(mem):
        for i in range(addr-len(mem)+1):
            mem+=[0]
    mem[addr]=data
    modified=True
    lastchange=True

def clrmm():
    esclocate(0,BOTTOMLN)
    esccolor(6)
    print(" "*79,end='')

def stdmm(s):
    global scriptingflag,verbose
    if scriptingflag:
        if verbose:
            print(s)
    else:
        clrmm()
        esccolor(4)
        esclocate(0,BOTTOMLN)
        print(s,end='',flush=True)

def jump(addr):
    global homeaddr,curx,cury
    if addr < homeaddr or addr>=homeaddr+LENONSCR:
        homeaddr=addr & ~(0xff)
    i=addr-homeaddr
    curx=(i&0xf)*2
    cury=(i//16)

def disp_marks():
    j=0
    esclocate(0,BOTTOMLN)
    esccolor(7)
    for i in 'abcdefghijklmnopqrstuvwxyz':
        m=mark[j]
        if m==UNKNOWN:
            print(f"{i} = unknown         ",end='')
        else:
            print(f"{i} = {mark[j]:012X}    ",end='')
        j+=1
        if j%3==0:
            print()
    esccolor(4)
    print("[ hit any key ]")
    getch()
    escclear()

def invoke_shell(line):
    esccolor(7)
    print()
    os.system(line.lstrip())
    esccolor(4)
    print("[ Hit any key to return ]",end='',flush=True)
    getch()
    escclear()

def expression(s,idx):
    x,idx=get_value(s,idx)
    if len(s)>idx and x!=UNKNOWN and s[idx]=='+':
        y,idx=get_value(s,idx+1)
        x=x+y
    elif len(s)>idx and x!=UNKNOWN and s[idx]=='-':
        y,idx=get_value(s,idx+1)
        x=x-y
    return x,idx

def get_value(s,idx):
    if idx>=len(s):
        return UNKNOWN,idx
    idx=skipspc(s,idx)
    ch=s[idx]
    if ch=='$':
        idx+=1
        v=len(mem)-1
    elif ch=='.':
        idx+=1
        v=fpos()
    elif ch=='\'' and len(s)>idx+1 and 'a'<=s[idx+1]<='z':
        idx+=1
        v=mark[ord(s[idx])-ord('a')]
        if v==UNKNOWN:
            stdmm("Unknown mark.")
            return UNKNOWN,idx-1
        else:
            idx+=1
    elif idx<len(s) and s[idx] in '0123456789abcdefABCDEF':
        x=0
        while idx<len(s) and s[idx] in '0123456789abcdefABCDEF':
            x=16*x+int("0x"+s[idx],16)
            idx+=1
        v=x
    elif ch=='#':
        x=0
        idx+=1
        while idx<len(s) and s[idx] in '0123456789':
            x=10*x+int(s[idx])
            idx+=1
        v=x
    else:
        v=UNKNOWN
    return v,idx

def acommand(start,end,line,idx):
    global span,nff
    nff=False
    idx=skipspc(line,idx)
    f=False

    m=''
    hs=[]
    if idx<len(line) and line[idx]=='/':
        idx+=1
        f=True
        if idx<len(line) and line[idx]!='/':
            m,idx=get_restr(line,idx)
            re_=True
        elif idx<len(line) and line[idx]=='/':
            hs,idx=get_hexs(line,idx+1)
            re_=False

    if idx<len(line) and line[idx]=='/' and f==True:
        idx+=1
        if idx<len(line) and line[idx]!='/':
            str_,idx=get_restr(line,idx)
            n=[ ord(c) for c in str_]
        elif idx<len(line) and line[idx]=='/':
            idx+=1
            n,idx=get_hexs(line,idx)
        else:
            stdmm("Unrecognized command.")
    else:
        stdmm("Unrecognized command.")

    orgpos=fpos()
    jump(start)
    if re_==True:
        f=searchstr(m)
        i=fpos()
    else:
        f=searchhex(hs)
        span=len(hs)
        i=fpos()

    while i<=end and f:
        delmem(i,i+span-1,False)
        insmem(i,n)
        i=i-span+len(n)
        f=searchnext(i)
        i=fpos()

    jump(orgpos)

def opeand(x,x2,x3):
    for i in range(x,x2+1):
        setmem(i,readmem(i)&(x3&0xff))
    return
            
def opeor(x,x2,x3):
    for i in range(x,x2+1):
        setmem(i,readmem(i)|(x3&0xff))
    return
            
def opexor(x,x2,x3):
    for i in range(x,x2+1):
        setmem(i,readmem(i)^(x3&0xff))
    return
            
def openot(x,x2):
    for i in range(x,x2+1):
        setmem(i,(~(readmem(i))&0xff))
    return
            
def srematch(a,b):
    global span
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    tty.setraw(fd)
    span=0
    f=re.match(a, b)
    termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
    if f:
        start,end=f.span()
        span=end-start
        return span
    else:
        return 0

def hitre(addr):
    global mem,remem
    s=''
    if not remem:
        return True
    for i in range(addr,len(mem)):
        s+=chr(mem[i])

    return srematch(remem,s)

def hit(addr):
    global smem,mem
    for i in range(len(smem)):
        if addr+i<len(mem) and mem[addr+i]==smem[i]:
            continue
        else:
            return False
    return True

def searchnext(fp):
    global smem,nff
    curpos=fp
    start=fp
    if regexp==False and not smem:
        return False
    while True:
        if regexp:
            f=hitre(curpos)
        else:
            f=hit(curpos)

        if f:
            jump(curpos)
            return True

        curpos+=1

        if curpos>=len(mem):
            if nff:
                stdmm("Search reached to bottom, continuing from top.")
            curpos=0
            esccolor(0)

        if curpos==start:
            if nff:
                stdmm("Not found.")
            return False

def searchlast(fp):
    curpos=fp
    start=fp
    if regexp==False and not smem:
        return False
    while True:
        if regexp:
            f=hitre(curpos)
        else:
            f=hit(curpos)

        if f:
            jump(curpos)
            return True

        curpos-=1
        if curpos<0:
            stdmm("Search reached to top, continuing from bottom.")
            esccolor(0)
            curpos=len(mem)-1

        if curpos==start:
            stdmm("Not found.")
            return False

def get_restr(s,idx):
    m=''
    while idx<len(s):
        ch=s[idx]
        if s[idx]=='\\':
            if idx+1<len(s):
                ch=s[idx+1]
        if s[idx]=='/':
            return m,idx
        m+=ch
        idx+=1
    return m,idx

def searchstr(s):
    global regexp,remem
    if s!="":
        regexp=True
        remem=s
        return(searchnext(fpos()))
    return False

def searchsub(line):
    if len(line)>2 and line[0:2]=='//':
        sm,idx=get_hexs(line,2)
        return searchhex(sm)
    elif len(line)>1 and line[0]=='/':
        m,idx=get_restr(line,1)
        return searchstr(m)

def search():
    esclocate(0,BOTTOMLN)
    esccolor(7)
    print("/",end='',flush=True)
    s="/"+getln()
    searchsub(s)

def get_hexs(s,idx):
    m=[]
    while idx<len(s):
        v,idx=expression(s,idx)
        if v==UNKNOWN:
            break
        m+=[v]
    return m,idx

def searchhex(sm):
    global smem,remem,regexp
    remem=''
    regexp=False
    if sm:
        smem=sm
        return(searchnext(fpos()))
    return False


def comment(line):
    """
    文字列 line から、'\'でエスケープされない';'以降を無視し、
    '\'でエスケープされた';'は';'に置き換える関数。

    Args:
        line: 処理対象の文字列。

    Returns:
        処理後の文字列。
    """
    result = []
    escaped = False
    ignore = False
    for char in line:
        if ignore:
            continue
        if char == '\\':
            escaped = True
            continue
        if char == ';' and not escaped:
            ignore = True
        elif char == ';' and escaped:
            result.append(';')
            escaped = False
        else:
            result.append(char)
            escaped = False
    return "".join(result)

def scripting(scriptfile):
    global scriptingflag,verbose
    try:
        f=open(scriptfile,"rt")
    except:
        stdmm("Script file open error.")
        return False
    scriptingflag=True
    line=f.readline().strip()
    flag=-1
    while line:
        if verbose:
            print(line)
        flag=commandline(line)
        if flag==0:
            f.close()
            return 0
        elif flag==1:
            f.close()
            return 1
        line=f.readline().strip()
    f.close()
    return 0

def left_shift_byte(x,x2,c):
    for i in range(x,x2+1):
        setmem(i,(readmem(i)<<1)|(c&1))
    return

def right_shift_byte(x,x2,c):
    for i in range(x,x2+1):
        setmem(i,(readmem(i)>>1)|((c&1)<<7))
    return

def left_rotate_byte(x,x2):
    for i in range(x,x2+1):
        m=readmem(i)
        c=(m&0x80)>>7
        setmem(i,(m<<1)|c)
    return

def right_rotate_byte(x,x2):
    for i in range(x,x2+1):
        m=readmem(i)
        c=(m&0x01)<<7
        setmem(i,(m>>1)|c)
    return

def get_multibyte_value(x,x2):
    v=0
    for i in range(x2,x-1,-1):
        v=(v<<8)|readmem(i)
    return v

def put_multibyte_value(x,x2,v):
    for i in range(x,x2+1):
        setmem(i,v&0xff)
        v>>=8
    return
    
def left_shift_multibyte(x,x2,c):
    v=get_multibyte_value(x,x2)
    put_multibyte_value(x,x2,(v<<1)|c)
    return

def right_shift_multibyte(x,x2,c):
    v=get_multibyte_value(x,x2)
    put_multibyte_value(x,x2,(v>>1)|(c<<((x2-x)*8+7)))
    return

def left_rotate_multibyte(x,x2):
    v=get_multibyte_value(x,x2)
    c=1 if v&(1<<((x2-x)*8+7)) else 0
    put_multibyte_value(x,x2,(v<<1)|c)
    return

def right_rotate_multibyte(x,x2):
    v=get_multibyte_value(x,x2)
    c=1 if v&0x1 else 0
    put_multibyte_value(x,x2,(v>>1)|(c<<((x2-x)*8+7)))
    return

def shift_rotate(x,x2,times,bit,multibyte,direction):
    for i in range(times):
        if not multibyte:
            if bit!=0 and bit!=1:
                if direction=='<':
                    left_rotate_byte(x,x2)
                else:
                    right_rotate_byte(x,x2)
            else:
                if direction=='<':
                    left_shift_byte(x,x2,bit&1)
                else:
                    right_shift_byte(x,x2,bit&1)
        else:
            if bit!=0 and bit!=1:
                if direction=='<':
                    left_rotate_multibyte(x,x2)
                else:
                    right_rotate_multibyte(x,x2)
            else:
                if direction=='<':
                    left_shift_multibyte(x,x2,bit&1)
                else:
                    right_shift_multibyte(x,x2,bit&1)
    return

def commandline(line):
    global lastchange,yank,filename,stack,verbose,scriptingflag

    if line=='':
        return -1
    line=comment(line)
    if line=='q':
        if lastchange:
            stdmm("No write since last change. To overriding quit, use 'q!'.")
            return -1
        return 0
    elif line=='q!':
        return 0
    elif line=='wq' or line=='wq!':
        f=writefile(filename)
        if f:
            lastchange=False
            return 0
        else:
            return -1
    elif line[0]=='w':
        if len(line)>=2:
            s=line[1:].lstrip()
            writefile(s)
        else:
            writefile(filename)
            lastchange=False
        return -1
    elif line[0]=='T' or line[0]=='t':
        if len(line)>=2:
            s=line[1:].lstrip()
            stack+=[scriptingflag]
            stack+=[verbose]
            verbose=True if line[0]=='T' else False
            print("")
            scripting(s)
            if verbose:
                stdmm("[ Hit any key ]")
                getch()
            verbose=stack[len(stack)-1]
            stack=stack[0:len(stack)-1]
            scriptingflag=stack[len(stack)-1]
            stack=stack[0:len(stack)-1]
            escclear()
            return -1
        else:
            stdmm("Specify script file name.")
            return -1
    elif line[0]=='n':
        searchnext(fpos()+1)
        return -1
    elif line[0]=='N':
        searchlast(fpos()-1)
        return -1
    elif line[0]=='!':
        if len(line)>=2:
            invoke_shell(line[1:])
            return -1
        return -1
    elif line[0]=='/':
        searchsub(line)
        return -1
    idx=skipspc(line,0)

    x,idx=expression(line,idx)
    if x==UNKNOWN:
        x=fpos()
    x2=x

    idx=skipspc(line,idx)
    if idx<len(line) and line[idx]==',':
        idx+=1
        idx=skipspc(line,idx)
        if idx<len(line) and line[idx]=='%':
            idx+=1
            idx=skipspc(line,idx)
            t,idx=expression(line,idx)
            if t==UNKNOWN:
                t=1
            x2=x+t-1
        else:
            t,idx=expression(line,idx)
            if t==UNKNOWN:
                t=x
            x2=t
    else:
        x2=x

    idx=skipspc(line,idx)

    if idx==len(line):
        jump(x)
        return -1
    
    if idx<len(line) and line[idx]=='y':
        idx+=1
        idx=skipspc(line,idx)
        if idx<len(line) and line[idx]=='/':
            idx+=1
            if idx<len(line) and line[idx]=='/':
                yank,idx=get_hexs(line,idx+1)
            else:
                s,idx=get_restr(line,idx)
                yank=[ ord(c) for c in s ]
                
            stdmm(f"{len(yank)} bytes yanked.")
            return -1
        else:
            yankmem(x,x2)
            return -1

    if idx<len(line) and line[idx] == 'p':
        y = list(yank)
        ovwmem(x, y)
        jump(x + len(y))
        return -1

    if idx<len(line) and line[idx] == 'P':
        y = list(yank)
        insmem(x, y)
        jump(x + len(yank))
        return -1

    if idx+1<len(line) and line[idx]=='m':
        if 'a'<=line[idx+1]<='z':
            mark[ord(line[idx+1])-ord('a')]=x
        return -1

    if idx<len(line) and (line[idx]=='r' or line[idx]=='R'):
        ch=line[idx]
        idx+=1 
        if idx>=len(line):
            stdmm("File name not specified.")
            return -1
        fn=line[idx:].lstrip()
        if fn=="":
            stdmm("File name not specified.")
        else:
            try:
                f=open(fn,"rb")
                data=list(f.read())
                f.close()
            except:
                data=[]
                stdmm("File read error.")

        if ch=='r':
            ovwmem(x,data)
        elif ch=='R':
            insmem(x,data)

        return -1

    if idx<len(line) and (line[idx]=='s' or line[idx]=='S'):
        ch=line[idx]
        idx+=1
        l=[ord(c) for c in line[idx:]]
        if ch=='s':
            ovwmem(x,l)
        elif ch=='S':
            insmem(x,l)
        jump(x+len(l))
        return -1

    if idx<len(line) and line[idx]=='O':
        idx+=1
        m,idx=get_hexs(line,idx)
        insmem(x,m)
        jump(x+len(m))
        return -1

    if idx<len(line) and line[idx]=='o':
        idx+=1
        m,idx=get_hexs(line,idx)
        ovwmem(x,m)
        jump(x+len(m))
        return -1

    if idx<len(line) and line[idx]=='d':
        length,idx=expression(line,idx+1)

        if length==UNKNOWN:
            length=1

        idx=skipspc(line,idx)

        delmem(x,x+length-1,True)
        return -1
        stdmm("Unrecognized command.")
        return -1
        

    if idx<len(line) and line[idx] in 'iI':
        ch=line[idx]
        xp,idx=expression(line,idx+1)
        if xp==UNKNOWN:
            stdmm("Invalid syntax")
            return -1

        x3=UNKNOWN
        if idx<len(line) and line[idx]==',':
            x3,idx=expression(line,idx+1)

        if ch=='I':
            if x3!=UNKNOWN:
                data=[x3]*xp
                insmem(x,data)
                jump(x+len(data))
            else:
                m=redmem(x,x2)
                insmem(xp,m)
                jump(xp+len(m))
        elif ch=='i':
            if x3==UNKNOWN:
                x3=0x00
            data=[x3]*xp
            ovwmem(x,data)
            jump(x+len(data))
        return -1

    if idx<len(line):
        ch=line[idx]
    else:
        ch=''

    if ch=='d':
        delmem(x,x2,True)
        jump(x)
        return -1
    elif ch=='w':
        idx+=1
        fn=line[idx:].lstrip()
        wrtfile(x,x2,fn)
        return -1
    elif ch=='a':
        acommand(x,x2,line,idx+1)
        return -1

    if idx<len(line) and line[idx]=='~':
        ch=line[idx]
        idx+=1
        openot(x,x2)
        return -1

    if idx<len(line) and line[idx] in "fvc&|^<>":
        ch=line[idx]
        idx+=1
        if ch in '<>':
            if idx<len(line) and line[idx]==ch:
                idx+=1
                multibyte=True
            else:
                multibyte=False

            times,idx=expression(line,idx)

            if times==UNKNOWN:
                times=1

            if idx<len(line) and line[idx]==',':
                bit,idx=expression(line,idx+1)
            else:
                bit=UNKNOWN

            shift_rotate(x,x2,times,bit,multibyte,ch)
            return -1

        if ch in 'f':
            m,idx=get_hexs(line,idx)
            if len(m):
                data=m*((x2-x+1)//len(m))+m[0:((x2-x+1)%len(m))]
                ovwmem(x,data)
                jump(x)
            else:
                stdmm("Invalid syntax.")
            return -1

        x3,idx=expression(line,idx)
        if x3==UNKNOWN:
            stdmm("Invalid parameter.")
            return -1

        if ch=='c':
            cpymem(x,x2,x3)
            jump(x3)
            return -1
        elif ch=='v':
            movmem(x,x2,x3)
            jump(x3)
            return -1
        elif ch=='&':
            opeand(x,x2,x3)
            return -1
        elif ch=='|':
            opeor(x,x2,x3)
            return -1
        elif ch=='^':
            opexor(x,x2,x3)
            return -1
    stdmm("Unrecognized command.")
    return -1

def commandln():
    esclocate(0,BOTTOMLN)
    esccolor(7)
    putch(':')
    line=getln().lstrip()
    return commandline(line)

def fedit():
    global nff, yank, lastchange, modified, insmod, homeaddr, curx, cury
    stroke = False
    ch = ''
    while True:
        repaint()
        esclocate(curx // 2 * 3 + 13 + (curx & 1), cury + 3)
        ch = getch()
        nff = True

        if ch == chr(27):
            c2 = getch()
            c3 = getch()
            if c3 == 'A':
                ch = 'k'
            elif c3 == 'B':
                ch = 'j'
            elif c3 == 'C':
                ch = 'l'
            elif c3 == 'D':
                ch = 'h'
            elif c2==chr(91) and c3==chr(50):
                ch='i'

        clrmm()  # ここでメッセージ領域をクリア
        if ch == 'n':
            searchnext(fpos()+1)
            continue
        elif ch == 'N':
            searchlast(fpos()-1)
            continue

        elif ch == chr(2):
            if homeaddr >= 256:
                homeaddr -= 256
            else:
                homeaddr = 0
            continue
        elif ch == chr(6):
            homeaddr += 256
            continue
        elif ch == chr(0x15):
            if homeaddr >= 128:
                homeaddr -= 128
            else:
                homeaddr = 0
            continue
        elif ch == chr(4):
            homeaddr += 128
            continue
        elif ch == '^':
            curx = 0
            continue
        elif ch == '$':
            curx = 30
            continue
        elif ch == 'j':
            if cury < 19:
                cury += 1
            else:
                scrdown()
            continue
        elif ch == 'k':
            if cury > 0:
                cury -= 1
            else:
                scrup()
            continue
        elif ch == 'h':
            if curx > 0:
                curx -= 1
            else:
                if fpos() != 0:
                    curx = 31
                    if cury > 0:
                        cury -= 1
                    else:
                        scrup()
            continue
        elif ch == 'l':
            inccurx()
            continue
        elif ch == chr(12):
            escclear()
            repaint()
            continue
        elif ch == 'Z':
            if writefile(filename):
                return True
            else:
                continue
        elif ch == 'q':
            if lastchange:
                stdmm("No write since last change. To overriding quit, use 'q!'.")
                continue
            return False
        elif ch == 'M':
            disp_marks()
            continue
        elif ch == 'm':
            ch = getch().lower()
            if 'a' <= ch <= 'z':
                mark[ord(ch) - ord('a')] = fpos()
            continue
        elif ch == '/':
            search()
            continue
        elif ch == '\'':
            ch = getch().lower()
            if 'a' <= ch <= 'z':
                jump(mark[ord(ch) - ord('a')])
            continue
        elif ch == 'p':
            y = list(yank)
            ovwmem(fpos(), y)
            jump(fpos() + len(y))
            continue
        elif ch == 'P':
            y = list(yank)
            insmem(fpos(), y)
            jump(fpos() + len(yank))
            continue

        if ch == 'i':
            insmod = not insmod
            stroke = False
        elif ch in string.hexdigits:
            addr = fpos()
            c = int("0x" + ch, 16)
            sh = 4 if not curx & 1 else 0
            mask = 0xf if not curx & 1 else 0xf0
            if insmod:
                if not stroke and addr < len(mem):
                    insmem(addr, [c << sh])
                else:
                    setmem(addr, readmem(addr) & mask | c << sh)
                stroke = (not stroke) if not curx & 1 else False
            else:
                setmem(addr, readmem(addr) & mask | c << sh)
            inccurx()
        elif ch == 'x':
            delmem(fpos(), fpos(), False)
        elif ch == ':':
            f = commandln()
            if f == 1:
                return True
            elif f == 0:
                return False

def readfile(fn):
    global mem,newfile
    try:
        f=open(fn,"rb")
    except:
        newfile=True
        stdmm("<new file>")
        mem=[]
    else:
        newfile=False
        mem=list(f.read())
        f.close()

def writefile(fn):
    global mem
    try:
        f=open(fn,"wb")
        f.write(bytes(mem))
        f.close()
        stdmm("File written.")
        return True
    except:
        stdmm("Permission denied.")
        return False

def wrtfile(start,end,fn):
    global mem
    try:
        f=open(fn,"wb")
        for i in range(start,end+1):
            if i<len(mem):
                f.write(bytes([mem[i]]))
            else:
                f.write(bytes([0]))
        f.close()
        return True
    except:
        stdmm("Permission denied.")
        return False

def main():
    global filename,verbose
    parser = argparse.ArgumentParser()
    parser.add_argument('file', help='file to edit')
    parser.add_argument('-s', '--script', type=str, default='', metavar='script.bi', help='bi script file')
    parser.add_argument('-v', '--verbose', action='store_true', help='verbose when processing script')
    parser.add_argument('-w', '--write', action='store_true', help='write file when exiting script')
    args = parser.parse_args()
    filename=args.file
    script=args.script
    verbose=args.verbose
    wrtflg=args.write
    readfile(filename)

    if script:
        f=scripting(script)
        if wrtflg and lastchange:
            writefile(filename)
    else:
        if not newfile:
            escclear()
        fedit()
        esccolor(7)

if __name__=="__main__":
    main()

# -*- coding: utf-8 -*-
# Copyright © 2017 Kevin Thibedeau
# Distributed under the terms of the MIT license
from __future__ import print_function

import re, io, ast, pprint
from minilexer import MiniLexer

'''VHDL documentation parser'''

vhdl_tokens = {
  'root': [
    (r'package\s+(\w+)\s+is', 'package', 'package'),
    (r'function\s+(\w+|"[^"]+")\s*\(', 'function', 'param_list'),
    (r'procedure\s+(\w+)\s*\(', 'procedure', 'param_list'),
    (r'function\s+(\w+)', 'function', 'simple_func'),
    (r'component\s+(\w+)\s*is', 'component', 'component'),
    (r'--.*\n', None),
  ],
  'package': [
    (r'function\s+(\w+|"[^"]+")\s*\(', 'function', 'param_list'),
    (r'procedure\s+(\w+)\s*\(', 'procedure', 'param_list'),
    (r'function\s+(\w+)', 'function', 'simple_func'),
    (r'component\s+(\w+)\s*is', 'component', 'component'),
    (r'subtype\s+(\w+)\s+is\s+(\w+)', 'subtype'),
    (r'constant\s+(\w+)\s+:\s+(\w+)', 'constant'),
    (r'type\s+(\w+)\s*is', 'type', 'type_decl'),
    (r'end\s+package', None, '#pop'),
    (r'--#+(.*)\n', 'metacomment'),
    (r'--.*\n', None),
  ],
  'type_decl': [
    (r'array', 'array_type', '#pop'),
    (r'file', 'file_type', '#pop'),
    (r'access', 'access_type', '#pop'),
    (r'record', 'record_type', '#pop'),
    (r'range', 'range_type', '#pop'),
    (r'\(', 'enum_type', '#pop'),
    (r';', 'incomplete_type', '#pop'),
    (r'--.*\n', None),
  ],
  'param_list': [
    (r'\s*((?:variable|signal|constant|file)\s+)?(\w+)\s*', 'param'),
    (r'\s*,\s*', None),
    (r'\s*:\s*', None, 'param_type'),
    (r'--.*\n', None),
  ],
  'param_type': [
    (r'\s*((?:in|out|inout|buffer)\s+)?(\w+)\s*', 'param_type'),
    (r'\s*;\s*', None, '#pop'),
    (r"\s*:=\s*('.'|[^\s;)]+)", 'param_default'),
    (r'\)\s*(?:return\s+(\w+)\s*)?;', 'end_subprogram', '#pop:2'),
    (r'\)\s*(?:return\s+(\w+)\s*)?is', None, '#pop:2'),
    (r'--.*\n', None),
  ],
  'simple_func': [
    (r'\s+return\s+(\w+)\s*;', 'end_subprogram', '#pop'),
    (r'\s+return\s+(\w+)\s+is', None, '#pop'),
    (r'--.*\n', None),
  ],
  'component': [
    (r'generic\s*\(', None, 'generic_list'),
    (r'port\s*\(', None, 'port_list'),
    (r'end\s+component\s*;', 'end_component', '#pop'),
    (r'--.*\n', None),
  ],
  'generic_list': [
    (r'\s*(\w+)\s*', 'generic_param'),
    (r'\s*,\s*', None),
    (r'\s*:\s*', None, 'generic_param_type'),
    (r'--#+(.*)\n', 'metacomment'),
    (r'--.*\n', None),
  ],
  'generic_param_type': [
    (r'\s*(\w+)\s*', 'generic_param_type'),
    (r'\s*;\s*', None, '#pop'),
    (r"\s*:=\s*([\w']+)", 'generic_param_default'),
    (r'\)\s*;', 'end_generic', '#pop:2'),
    (r'--#+(.*)\n', 'metacomment'),
    (r'--.*\n', None),
  ],
  'port_list': [
    (r'\s*(\w+)\s*', 'port_param'),
    (r'\s*,\s*', None),
    (r'\s*:\s*', None, 'port_param_type'),
    (r'--#\s*{{(.*)}}\n', 'section_meta'),
    (r'--#+(.*)\n', 'metacomment'),
    (r'--.*\n', None),
  ],
  'port_param_type': [
    (r'\s*(in|out|inout|buffer)\s+(\w+)\s*\(', 'port_array_param_type', 'array_range'),
    (r'\s*(in|out|inout|buffer)\s+(\w+)\s*', 'port_param_type'),
    (r'\s*;\s*', None, '#pop'),
    (r"\s*:=\s*([\w']+)", 'port_param_default'),
    (r'\)\s*;', 'end_port', '#pop:2'),
    (r'--#+(.*)\n', 'metacomment'),
    (r'--.*\n', None),
  ],
  'array_range': [
    (r'\(', 'open_paren', 'nested_parens'),
    (r'\)', 'array_range_end', '#pop'),
  ],
  'nested_parens': [
    (r'\(', 'open_paren', 'nested_parens'),
    (r'\)', 'close_paren', '#pop'),
  ]
}
      
VhdlLexer = MiniLexer(vhdl_tokens)


class VhdlObject(object):
  def __init__(self, name, desc=None):
    self.name = name
    self.kind = 'unknown'
    self.desc = desc

class VhdlParameter(object):
  def __init__(self, name, mode=None, data_type=None, default_value=None, desc=None):
    self.name = name
    self.mode = mode
    self.data_type = data_type
    self.default_value = default_value
    self.desc = desc

  def __str__(self):
    if self.mode is not None:
      param = '{} : {} {}'.format(self.name, self.mode, self.data_type)
    else:
      param = '{} : {}'.format(self.name, self.data_type)
    if self.default_value is not None:
      param = '{} := {}'.format(param, self.default_value)
    return param
      
  def __repr__(self):
    return "VhdlParameter('{}')".format(self.name)

class VhdlPackage(VhdlObject):
  def __init__(self, name, desc=None):
    VhdlObject.__init__(self, name, desc)
    self.kind = 'package'

class VhdlType(VhdlObject):
  def __init__(self, name, type_of, desc=None):
    VhdlObject.__init__(self, name, desc)
    self.kind = 'type'
    self.type_of = type_of
  def __repr__(self):
    return "VhdlType('{}', '{}')".format(self.name, self.type_of)


class VhdlSubtype(VhdlObject):
  def __init__(self, name, base_type, desc=None):
    VhdlObject.__init__(self, name, desc)
    self.kind = 'subtype'
    self.base_type = base_type
  def __repr__(self):
    return "VhdlSubtype('{}', '{}')".format(self.name, self.base_type)


class VhdlConstant(VhdlObject):
  def __init__(self, name, base_type, desc=None):
    VhdlObject.__init__(self, name, desc)
    self.kind = 'constant'
    self.base_type = base_type
  def __repr__(self):
    return "VhdlConstant('{}', '{}')".format(self.name, self.base_type)


class VhdlFunction(VhdlObject):
  def __init__(self, name, parameters, return_type=None, desc=None):
    VhdlObject.__init__(self, name, desc)
    self.kind = 'function'
    self.parameters = parameters
    self.return_type = return_type

class VhdlProcedure(VhdlObject):
  def __init__(self, name, parameters, desc=None):
    VhdlObject.__init__(self, name, desc)
    self.kind = 'procedure'
    self.parameters = parameters


class VhdlComponent(VhdlObject):
  def __init__(self, name, ports, generics=None, sections=None, desc=None):
    VhdlObject.__init__(self, name, desc)
    self.kind = 'component'
    self.generics = generics if generics is not None else []
    self.ports = ports
    self.sections = sections if sections is not None else {}
  def __repr__(self):
    return "VhdlComponent('{}')".format(self.name)


def parse_vhdl_file(fname):
  with open(fname, 'rt') as fh:
    text = fh.read()
  return parse_vhdl(text)

def parse_vhdl(text):
  lex = VhdlLexer
  
  name = None
  kind = None
  saved_type = None

  metacomments = []
  parameters = []
  param_items = []

  generics = []
  ports = []
  sections = []
  port_param_index = 0
  last_item = None
  array_range_start_pos = 0

  objects = []
  
  #print('## PARSE VHDL:', text)

  for pos, action, groups in lex.run(text):
    if action == 'metacomment':
      if last_item is None:
        metacomments.append(groups[0])
      else:
        last_item.desc = groups[0]
    if action == 'section_meta':
      sections.append((port_param_index, groups[0]))

    elif action == 'function':
      kind = 'function'
      name = groups[0]
      param_items = []
      parameters = []
    elif action == 'procedure':
      kind = 'procedure'
      name = groups[0]
      param_items = []
      parameters = []
    elif action == 'param':
      # Complete previous parameters
      for i in param_items:
        parameters.append(i)
      param_items = []

      #param_items.append(groups[1])
      param_items.append(VhdlParameter(groups[1]))
    elif action == 'param_type':
      mode, ptype = groups
      
      #if mode is None:
      #  mode = 'in'
      
      if mode is not None:
        mode = mode.strip()
      
      for i in param_items:
        #parameters.append(VhdlParameter(i, mode, ptype))
        i.mode = mode
        i.data_type = ptype
      #param_items = []
    elif action == 'param_default':
      #print('## DEFAULT:', name, groups[0])
      for i in param_items:
        i.default_value = groups[0]

    elif action == 'end_subprogram':
      # Complete last parameters
      for i in param_items:
        parameters.append(i)
        
      if kind == 'function':
        vobj = VhdlFunction(name, parameters, groups[0], metacomments)
      else:
        vobj = VhdlProcedure(name, parameters, metacomments)
      
      objects.append(vobj)
    
      metacomments = []
      parameters = []
      param_items = []
      kind = None
      name = None
    elif action == 'component':
      kind = 'component'
      name = groups[0]
      generics = []
      ports = []
      param_items = []
      sections = []
      port_param_index = 0
    elif action == 'generic_param':
      param_items.append(groups[0])
    elif action == 'generic_param_type':
      ptype = groups[0]
      
      for i in param_items:
        generics.append(VhdlParameter(i, 'in', ptype))
      param_items = []
      last_item = generics[-1]
      
    elif action == 'port_param':
      param_items.append(groups[0])
      port_param_index += 1
    elif action == 'port_param_type':
      mode, ptype = groups

      for i in param_items:
        ports.append(VhdlParameter(i, mode, ptype))
        
      param_items = []
      last_item = ports[-1]

    elif action == 'port_array_param_type':
      mode, ptype = groups
      array_range_start_pos = pos[1]

    elif action == 'array_range_end':
      arange = text[array_range_start_pos:pos[0]+1]

      for i in param_items:
        ports.append(VhdlParameter(i, mode, ptype + arange))

      param_items = []
      last_item = ports[-1]

    elif action == 'end_component':
      vobj = VhdlComponent(name, ports, generics, dict(sections), metacomments)
      objects.append(vobj)
      last_item = None
      metacomments = []
      
    elif action == 'package':
      objects.append(VhdlPackage(groups[0]))
      kind = None
      name = None
    elif action == 'type':
      saved_type = groups[0]

    elif action in ('array_type', 'file_type', 'access_type', 'record_type', 'range_type', 'enum_type', 'incomplete_type'):
      vobj = VhdlType(saved_type, action, metacomments)
      objects.append(vobj)
      kind = None
      name = None
      metacomments = []
    elif action == 'subtype':
      vobj = VhdlSubtype(groups[0], groups[1], metacomments)
      objects.append(vobj)
      kind = None
      name = None
      metacomments = []
    elif action == 'constant':
      vobj = VhdlConstant(groups[0], groups[1], metacomments)
      objects.append(vobj)
      kind = None
      name = None
      metacomments = []


  return objects


def subprogram_prototype(vo):
  '''Generate a canonical prototype string'''

  plist = '; '.join(str(p) for p in vo.parameters)
  
  if isinstance(vo, VhdlFunction):
    if len(vo.parameters) > 0:
      proto = 'function {}({}) return {};'.format(vo.name, plist, vo.return_type)
    else:
      proto = 'function {} return {};'.format(vo.name, vo.return_type)
    
  else: # procedure
    proto = 'procedure {}({});'.format(vo.name, plist)
  
  #print('## PROTO:', proto)
  return proto

def subprogram_signature(vo, fullname=None):
  '''Generate a signature string'''
  
  if fullname is None:
    fullname = vo.name

  if isinstance(vo, VhdlFunction):
    plist = ','.join(p.data_type for p in vo.parameters)
    sig = '{}[{} return {}]'.format(fullname, plist, vo.return_type)
  else: # procedure
    plist = ','.join(p.data_type for p in vo.parameters)
    sig = '{}[{}]'.format(fullname, plist)

  return sig




class VhdlExtractor(object):
  '''Utility class that caches parsed objects and tracks array type definitions'''
  def __init__(self, array_types=set()):
    self.array_types = set(('std_ulogic_vector', 'std_logic_vector',
      'signed', 'unsigned', 'bit_vector'))

    self.array_types |= array_types
    self.object_cache = {}

    
  def extract_file_objects(self, fname):
    objects = []
    if fname in self.object_cache:
      objects = self.object_cache[fname]
    else:
      with io.open(fname, 'rt', encoding='latin-1') as fh:
        text = fh.read()
        objects = parse_vhdl(text)
        self.object_cache[fname] = objects
        self.register_array_types(objects)

    return objects


  def extract_file_components(self, fname):
    objects = self.extract_file_objects(fname)
    comps = [o for o in objects if isinstance(o, VhdlComponent)]
    return comps

  def extract_components(self, text):
    objects = parse_vhdl(text)
    self.register_array_types(objects)
    comps = [o for o in objects if isinstance(o, VhdlComponent)]
    return comps
  

  def is_array(self, data_type):
    '''Check if a type is a known array type'''
    return data_type.lower() in self.array_types

    
  def add_array_types(self, type_defs):
    '''Add array data types to internal registry'''
    if 'arrays' in type_defs:
      self.array_types |= set(type_defs['arrays'])
      
  def load_array_types(self, fname):
    '''Load file of previously extracted data types'''
    type_defs = ''
    with open(fname, 'rt') as fh:
      type_defs = fh.read()
    
    try:
      type_defs = ast.literal_eval(type_defs)
    except SyntaxError:
      type_defs = {}
      
    self.add_array_types(type_defs)
      
  def save_array_types(self, fname):
    '''Save array type registry to a file'''
    type_defs = {'arrays': sorted(list(self.array_types))}
    with open(fname, 'wt') as fh:
      pprint(type_defs, stream=fh)

  def register_array_types(self, objects):
  
    # Add all array types directly
    types = [o for o in objects if isinstance(o, VhdlType) and o.type_of == 'array_type']
    for t in types:
      self.array_types.add(t.name)

    subtypes = {o.name:o.base_type for o in objects if isinstance(o, VhdlSubtype)}

    # Find all subtypes of an array type
    for k,v in subtypes.iteritems():
      while v in subtypes: # Follow subtypes of subtypes
        v = subtypes[v]
      if v in self.array_types:
        self.array_types.add(k)

  def register_files_array_types(self, files):
    for fname in files:
      self.register_array_types(self.extract_file_objects(fname))


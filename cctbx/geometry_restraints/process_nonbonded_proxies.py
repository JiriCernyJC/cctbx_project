from __future__ import division, print_function
import math
from libtbx import group_args
from scitbx import matrix
from libtbx.str_utils import make_sub_header
from libtbx.utils import null_out
import scitbx.matrix
from cctbx import sgtbx
from libtbx.test_utils import approx_equal
from collections import OrderedDict
import six


def check_if_1_5_interaction(
      i_seq,
      j_seq,
      hd_sel,
      full_connectivity_table):
  """
  Checks if there is 1-5 interaction between a hydrogen (H) and heavy atom (X): H-A-A-A-X

  Parameters:
    i_seq (int): atom i_seq
    j_seq (int): atom i_seq
    hd_sel (bool array)        hd_sel[i] returns True of False if atom i is H or not
    full_connectivity_table (dict of lists of int):  dictionary with a list
                                             of all atoms connected to atom i

  Returns:
    bool: True/False if there is 1-5 hydrogen and heavy atom interaction
  """
  # check if there is hydrogen - heavy atom interaction
  xor = lambda a,b: (a or b) and not (a and b)
  if xor(hd_sel[i_seq],hd_sel[j_seq]):
    # starting with hydrogen will make process shorter
    if not hd_sel[i_seq]:
      i_seq,j_seq = j_seq,i_seq
    # build connection table of i_seq, 4 steps deep
    atoms_numbers = dict([(i_seq, 0)]) # i_seq is in zero distance
    used_connections = {i_seq}
    new_connections = {i_seq}
    for i in range(2,6):
      connections = set()
      for key in new_connections:
        # add all new connections for the current step
        connections = connections.union(set(full_connectivity_table[key]))
      # Remove the connection that were already used
      new_connections = connections - used_connections
      # Add the new connection to the used ones
      used_connections = used_connections.union(connections)
      # Add the new atoms with their distance from key
      for new_atom in new_connections:
        atoms_numbers[new_atom] = i
    # return true if j_seq in the is 1-5 connection
    return (j_seq in atoms_numbers) and (atoms_numbers[j_seq] == 5)
  else:
    return False


def cos_vec(u, v, w):
  """
  Calculate the cosine to evaluate whether clashing atoms are inline
  A1 clashes with A2 and A3. Find out if A2 and A3 are inline.
  A1 ~~~ A2
  A1 ~~~ A3

  Parameters:
  u: vector of clashing atom (A2 or A3, order does not matter)
  v: vector of clashing atom (A2 or A3, order does not matter)
  w: vector of common clashing atom (A1)

  Returns:
    float (cos_angle): the cosine of the angle between center of the common atom
      and the mid point between the other two atoms.
  """
  u = matrix.col(u)
  v = matrix.col(v)
  w = matrix.col(w)

  vec1 = w - (u/2 + v/2)
  vec2 = u - v

  try:
    cos_angle = abs(vec1.normalize().dot(vec2.normalize()))
  except ZeroDivisionError:
    cos_angle = 1
  return cos_angle


def unknown_pairs_present(model):
  """
  Test if PDB file contains unknown type pairs

  Parameters:
    model (obj): model object

  Returns:
    (bool): True if PDB file contains unknown type pairs
  """
  grm = model.get_restraints_manager()
  sites_cart = model.get_sites_cart()
  site_labels = model.get_xray_structure.scatterers().extract_labels()
  pp= grm.pair_proxies(sites_cart=sites_cart,site_labels=site_labels)
  return (pp.nonbonded_proxies.n_unknown_nonbonded_type_pairs != 0)


class clashes(object):
  """
  Class for clashes
  """
  def __init__(self, clashes_dict, model):
    '''
    clashes_dict  {(iseq, jseq):(distance, sum_vdw_radii)}
    iseq          atom i
    jseq          atom j
    distance      distance between atom i and atom j
    sum_vdw_radii sum of vdW radii
    '''
    self._clashes_dict = clashes_dict
    self.model = model
    #
    self.sort_clashes()


  def show(self, log=null_out(), show_clashscore=True):
    """
    Print all clashes in a table.
    """
    make_sub_header(' Nonbonded overlaps', out=log)
    if self._clashes_dict:
      # General information
      results = self.get_results()
      result_str = '{:<18} : {:5d}'
      print(result_str.format(' Number of clashes', results.n_clashes), file=log)
      print(result_str.format(' Number of clashes due to symmetry', results.n_clashes_sym), file=log)
      result_str = '{:<18} : {:5.2f}'
      if show_clashscore:
        print(result_str.format(' Clashscore', results.clashscore), file=log)
      # print table with all overlaps
      labels =  ["Overlapping residues info","model distance","overlap",
                 "symmetry"]
      lbl_str = '{:^33}|{:^16}|{:^11}|{:^15}'
      table_str = '{:>16}|{:>16}|{:^16.2f}|{:^11.2}|{:^15}|'
      print('\n' + lbl_str.format(*labels), file=log)
      print('-'*78, file=log)
      atoms = self.model.get_atoms()
      for iseq_tuple, record in six.iteritems(self._clashes_dict):
        i_seq, j_seq = iseq_tuple
        overlap = record[2]
        if record[4] is not None:
          symop = record[4]
        else: symop = ''
        i_id_str = atoms[i_seq].id_str().replace('pdb=','').replace('"','')
        j_id_str = atoms[j_seq].id_str().replace('pdb=','').replace('"','')
        line = [i_id_str, j_id_str,round(record[0], 2),round(overlap, 2), symop]
        print(table_str.format(*line), file=log)
      print('-'*78, file=log)
    else:
      print('No clashes found', file=log)


  def add_clash(self, clash_tuple, clash_info):
    """
    Add a clash to the dictionary

    Parameters:
      clash_tuple (tuple): tuple of 2 i_seqs
      clash_info (list): list of: [model_distance, vdw_sum, abs(delta), symop_str, symop]
    """
    self._clashes_dict[clash_tuple] = clash_info


  def remove_clash(self, clash_tuple):
    """
    Remove a clash from the dictionary

    Parameters:
      clash_tuple(tuple): tuple of 2 i_seqs
    """
    if clash_tuple in self._clashes_dict:
      del self._clashes_dict[clash_tuple]


  def iseq_tuple_is_sym_clash(self, clash_tuple):
    """
    Test if clash tuple is involved in symmetry clash
    """
    return self._clashes_dict[clash_tuple][4]


  def iseq_tuple_is_clashing(self, clash_tuple):
    """
    Test if two iseqs are involved in a clash
    """
    are_clashing = False
    if clash_tuple in self._clashes_dict:
      are_clashing = True
    return are_clashing


  def iseq_is_clashing(self, iseq):
    """
    Test if a particular atom is involved in a clash.

    Parameters:
      iseq (int): atom i_seq number

    Returns:
      (bool): True if the atom is involved in a clash
    """
    is_clashing = False
    if self._clashes_dict:
      i_seqs, j_seqs = zip(*self._clashes_dict)
      if iseq in i_seqs or iseq in j_seqs:
        is_clashing = True
    return is_clashing


  def get_model_distance(self, clash_tuple):
    """
    Return the model distance of a clash
    """
    return self._clashes_dict[clash_tuple][0]


  def get_n_clashes(self):
    """
    Number of clashes
    """
    return len(self._clashes_dict)


  def sort_clashes(self, by_value='overlap'):
    """
    Sort clashes according to vdW distance, model distance, overlap or symmetry

    Parameters:
      by_value (str): vdw_distance, model_distance, overlap or symmetry
    """
    options = ['vdw_distance', 'model_distance', 'overlap', 'symmetry']
    if (by_value not in options):
      raise Sorry('Can not sort by this value. Possible options: \n\
                  vdw_distance, model_distance, overlap, symmetry')
    if by_value == 'model_distance': key = 0
    if by_value == 'vdw_distance': key = 1
    if by_value == 'overlap': key = 2
    if by_value == 'symmetry': key = 4
    self._clashes_dict = OrderedDict(
      sorted(self._clashes_dict.items(), key=lambda x: x[1][key]))


  def _obtain_symmetry_clashes(self):
    """
    Get clashes due to symmetry
    """
    self._symmetry_clashes_dict = dict()
    n_clashes_sym = 0
    clashscore_sym = 0
    for iseq_tuple, record in six.iteritems(self._clashes_dict):
      if record[4] is not None:
        self._symmetry_clashes_dict[iseq_tuple] = record
    if self._symmetry_clashes_dict:
      n_clashes_sym = len(self._symmetry_clashes_dict)
      # Does clashscore_sym actually make sense?
      n_atoms = self.model.size()
      clashscore_sym = n_clashes_sym * 1000 / n_atoms
    return n_clashes_sym, clashscore_sym


  def _obtain_macro_mol_clashes(self):
    """
    Get clashes involving macro-mol atoms only
    """
    self._macro_mol_clashes_dict = dict()
    n_clashes_macro_mol = 0
    clashscore_macro_mol = 0
    macro_mol_sel = self.model.selection(string = 'protein')
    for iseq_tuple, record in six.iteritems(self._clashes_dict):
      if (macro_mol_sel[iseq_tuple[0]] and macro_mol_sel[iseq_tuple[1]]
          and record[4] is None):
        self._macro_mol_clashes_dict[iseq_tuple] = record
    if self._macro_mol_clashes_dict:
      n_clashes_macro_mol = len(self._macro_mol_clashes_dict)
      clashscore_macro_mol = n_clashes_macro_mol * 1000 / self.model.select(macro_mol_sel).size()
    return n_clashes_macro_mol, clashscore_macro_mol


  def get_results(self):
    """
    Accessor for results
    """
    # overall
    n_clashes = self.get_n_clashes()
    n_atoms = self.model.size()
    clashscore = n_clashes * 1000 / n_atoms
    # due to symmetry
    n_clashes_sym, clashscore_sym = self._obtain_symmetry_clashes()
    # macromolecule ('protein')
    n_clashes_macro_mol, clashscore_macro_mol = self._obtain_macro_mol_clashes()

    return group_args(
             n_clashes      = n_clashes,
             clashscore     = clashscore,
             n_clashes_sym  = n_clashes_sym,
             clashscore_sym = clashscore_sym,
             n_clashes_macro_mol  = n_clashes_macro_mol,
             clashscore_macro_mol = clashscore_macro_mol)


class hbonds(object):
  '''
  Class for hbonds
  '''
  def __init__(self, hbonds_dict, model):
    '''
    hbonds_dict = {(iseq, jseq, kseq):(H_A_distance, X_A_distance, X_H_A_angle)}
    hydrogen bond: X-H...A
    iseq          atom X (donor heavy atom)
    jseq          atom H (donor H atom)
    kseq          atom A (acceptor atom)
    H_A_distance
    X_A_distance
    X_H_A_angle
    '''
    self._hbonds_dict = hbonds_dict
    self.model = model

  def show(self, log=null_out()):
    """
    Print all hbonds in a table.
    """
    make_sub_header(' Hydrogen bonds', out=log)
    if self._hbonds_dict:
      # General information
      results = self.get_results()
      result_str = '{:<18} : {:5d}'
      print(result_str.format(' Number of H bonds', results.n_hbonds), file=log)
      # print table with all H-bonds
      title1 = ['donor', 'acceptor', 'distance', 'angle']
      title1_str = '{:^33}|{:^16}|{:^21}|{:^14}|'
      print('\n' + title1_str.format(*title1), file=log)

      title2 =  ['X', 'H', 'A','H...A','X...A',
                 'X-H...A', 'symop']
      title2_str = '{:^16}|{:^16}|{:^16}|{:^10}|{:^10}|{:^14}|{:^15}|'
      print(title2_str.format(*title2), file=log)
#      lbl_str = '{:^49}|{:^16}|{:^11}|{:^15}'
#      table_str = '{:>16}|{:>16}|{:^16.2f}|{:^11.2}|{:^15}|'
      table_str = '{:>16}|{:>16}|{:^16}|{:^10.2f}|{:^10.2f}|{:^14.2f}|{:^15}|'
#      print(lbl_str.format(*labels), file=log)
      print('-'*99, file=log)
      atoms = self.model.get_atoms()
      for iseq_tuple, record in self._hbonds_dict.iteritems():
        iseq_x, iseq_h, iseq_a = iseq_tuple
        if record[4] is not None:
          symop = record[4]
        else: symop = ''
        x_id_str = atoms[iseq_x].id_str().replace('pdb=','').replace('"','')
        h_id_str = atoms[iseq_h].id_str().replace('pdb=','').replace('"','')
        a_id_str = atoms[iseq_a].id_str().replace('pdb=','').replace('"','')
        line = [x_id_str, h_id_str, a_id_str, round(record[0], 2),
          round(record[1], 2), round(record[2], 2), symop]
        print(table_str.format(*line), file=log)
      print('-'*99, file=log)
    else:
      print('No hbonds found', file=log)


  def get_n_hbonds(self):
    return len(self._hbonds_dict)

  def forms_hbond(self, iseq):
    pass

  def sort_hbonds(self, by_value='HA_distance'):
    pass

  def get_results(self):
    """
    Accessor for results
    """
    # overall
    n_hbonds = self.get_n_hbonds()
    # due to symmetry TODO
#    n_hbonds_sym = self._obtain_symmetry_clashes()

    return group_args(
             n_hbonds = n_hbonds)


class manager():

  def __init__(self,
               model):
    self.model = model
    #
    self._clashes = None
    self._hbonds  = None

    # add H in manager or do we enfore that input model has H?
    # self._add_H_atoms() ????


  def get_clashes(self):
    """
    Accessor for clashes object
    """
    if self._clashes is None:
      self._process_nonbonded_proxies(find_clashes = True)
    return self._clashes


  def get_hbonds(self):
    """
    Accessor for hbonds object
    """
    if not self._hbonds:
      self._process_nonbonded_proxies(find_hbonds = True)
    return self._hbonds


  def has_hbonds(self):
    """
    True/False if any hbonds were found.
    """
    hbonds = self.get_hbonds()
    return hbonds.get_n_bonds() > 0


  def has_clashes(self):
    """
    True/False if any clashes were found.
    """
    clashes = self.get_clashes()
    return clashes.get_n_clashes() > 0


  def show(self):
    """
    Print information
    """
    if self.has_clashes():
      self._clashes.show()
    if self.has_hbonds():
      self._hbonds.show()


  def _process_nonbonded_proxies(self,
                                 find_clashes = True,
                                 find_hbonds  = True):
    """
    Process nonbonded_proxies to find bonds, interactions and clashes.
    Clashes code refactored from Youval Dar's code for nonbonded_overlaps (LBNL 2013)
    """
    grm = self.model.get_restraints_manager().geometry
    xrs = self.model.get_xray_structure()
    sites_cart  = self.model.get_sites_cart()
    site_labels = xrs.scatterers().extract_labels()
    self.hd_sel      = self.model.get_hd_selection()
    self.water_sel   = self.model.selection('water')
    if self.model.crystal_symmetry() is not None:
      unit_cell   = self.model.crystal_symmetry().unit_cell()
    else:
      unit_cell = None
    self.atoms  = self.model.get_atoms()

    pair_proxies = grm.pair_proxies(
                        sites_cart  = sites_cart,
                        site_labels = site_labels)
    proxies_info_nonbonded = pair_proxies.nonbonded_proxies.get_sorted(
      by_value    = "delta",
      sites_cart  = sites_cart,
      site_labels = site_labels)

    if proxies_info_nonbonded is not None:
      nonbonded_list = proxies_info_nonbonded[0]
    else:
      nonbonded_list = []
      # create 'empty' instance of results class
      self._clashes = clashes(clashes_dict = dict())
      self._hbonds  = hbonds(hbonds_dict = dict())
      return

    fsc0 = grm.shell_sym_tables[0].full_simple_connectivity()
    fsc2 = grm.shell_sym_tables[2].full_simple_connectivity()

    #self._clashes_dict = dict()
    # Create clashes class
    self._clashes = clashes(
                      clashes_dict = dict(),
                      model        = self.model)
    self._hbonds_dict  = dict()
    self._mult_clash_dict = dict()

    # loop over nonbonded proxies, analyze and fill in the dicts:
    for item in nonbonded_list:
      i_seq          = item[1]
      j_seq          = item[2]
      model_distance = item[3]
      vdw_sum        = item[4]
      symop_str      = item[5] # TODO probably not necessary
      symop          = item[6]

      # TODO is this needed?
      is_hbond, is_clash = False, False

      if find_hbonds:
        if (model_distance < 3 and [self.hd_sel[i_seq],self.hd_sel[j_seq]].count(True) == 1):
          is_hbond = self._is_hbond(
                      item  = item,
                      unit_cell = unit_cell,
                      site_labels = site_labels,
                      fsc0 = fsc0)

      # proxy cannot be clash and hbond at the same time (?)

      # Find clashes
      if find_clashes:
        delta = model_distance - vdw_sum
        if (delta < -0.40):
          is_clash = self._is_clash(
                      i_seq = i_seq,
                      j_seq = j_seq,
                      fsc0 = fsc0,
                      model_distance = model_distance)
          if is_clash:
            clash_tuple = [i_seq, j_seq]
            clash_tuple.sort()
            clash_tuple = tuple(clash_tuple)
            clash_info = [model_distance, vdw_sum, abs(delta), symop_str, symop]
            self._clashes.add_clash(clash_tuple = clash_tuple,
                                    clash_info  = clash_info)
            #self._clashes_dict[(i_seq, j_seq)] = \
            #  [model_distance, vdw_sum, abs(delta), symop_str, symop]

    # Remove clashes involving common atoms (cannot be done in first loop!)
    self._process_clashes(sites_cart = sites_cart,
                          fsc0       = fsc0)
    self._clashes.sort_clashes(by_value='overlap')
    # Create clashes class
    #self._clashes = clashes(
    #                  clashes_dict = self._clashes_dict,
    #                  model        = self.model)

    self._hbonds = hbonds(
                     hbonds_dict = self._hbonds_dict,
                     model        = self.model)

  def _is_hbond(self,
                item,
                unit_cell,
                site_labels,
                fsc0):
    """
    Determine if a nonbonded proxy is a H bond
    """
    is_hbond = False

    i_seq          = item[1]
    j_seq          = item[2]
    model_distance = item[3]
    vdw_sum        = item[4]
    symop_str      = item[5]
    symop          = item[6]

    atom1 = self.atoms[i_seq]
    atom2 = self.atoms[j_seq]

    # TODO: Ignore water for now
    if self.water_sel[i_seq] or self.water_sel[j_seq]:
      return is_hbond
    # Ignore atoms within the same residue
    #if (atom1.is_in_same_conformer_as(atom2)):
    if (self.atoms[i_seq].parent().parent().id_str() ==
        self.atoms[j_seq].parent().parent().id_str()):
      return is_hbond

    rg1, rg2, atom1, atom2 = self._residue_groups_rt_mx_ij(atom1 = atom1,
                                                           atom2 = atom2,
                                                           unit_cell = unit_cell,
                                                           symop_str = symop_str,
                                                           symop = symop)
    # Assign donor H and acceptor A atoms
    if self.hd_sel[atom1.i_seq]:
      atom_h, rg_h = atom1, rg1
      atom_a, rg_a = atom2, rg2
    elif self.hd_sel[atom2.i_seq]:
      atom_h, rg_h = atom2, rg2
      atom_a, rg_a = atom1, rg1
    else:
      raise Sorry('this should not happen')

    # Filter acceptor atom element
    # TODO: this could be done earlier? To save calling self._residue_groups_rt_mx_ij
    element_a = atom_a.element.strip().upper()
    if element_a not in ["O","N","S","F","CL"]: return is_hbond
    # Find X atom of X-H group
    iseq_x_list = fsc0[atom_h.i_seq]
    # There can be several, if silly double conformation
    for iseq_x in iseq_x_list:
      atom_x = self.atoms[iseq_x]

      xyz_h = matrix.col(atom_h.xyz)
      xyz_a = matrix.col(atom_a.xyz)
      xyz_x = matrix.col(atom_x.xyz)

      h_a_distance = (xyz_h - xyz_a).length()
      # something went wrong if they are not equal
      assert approx_equal(h_a_distance, model_distance, eps=0.1)
      x_a_distance = (xyz_x - xyz_a).length()
      x_h_a_angle = (xyz_h - xyz_a).angle(xyz_h - xyz_x)

      # Values from Steiner, Angew. Chem. Int. Ed. 2002, 41, 48-76, Table 2
      # Modification: minimum angle is 110, not 90
      # TODO: do we want to adapt to acceptor element?
      # TODO: h_a_y angle could be interesting, too
      if ((h_a_distance >= 1.2 and h_a_distance <= 2.2) and
         (x_a_distance  >= 2.2 and x_a_distance <= 3.2) and
         (math.degrees(x_h_a_angle) >= 110)):
        is_hbond = True

        self._hbonds_dict[(atom_x.i_seq, atom_h.i_seq, atom_a.i_seq)] = \
          [h_a_distance, x_a_distance, math.degrees(x_h_a_angle), symop_str, symop, vdw_sum]
        # TODO: if several atom_x, use the first one found
        # Can be made smarter in the future (show shortest or both)
        break

    return is_hbond

    #print(h_a_distance, model_distance, x_a_distance, math.degrees(h_a_x_angle))


  def _residue_groups_rt_mx_ij(self, atom1, atom2, unit_cell, symop_str, symop):
    """
    Get atoms object and residue group object for H and heavy atom
    """
    xyzs1 = atom1.parent().parent().atoms().extract_xyz()
    xyzs2 = atom2.parent().parent().atoms().extract_xyz()

    rg1 = atom1.parent().parent().detached_copy()
    rg2 = atom2.parent().parent().detached_copy()
    if symop_str and unit_cell:
      rt_mx_ji = sgtbx.rt_mx(str(symop))
      xyzs2 = unit_cell.fractionalize(xyzs2)
      m3 = rt_mx_ji.r().as_double()
      m3 = scitbx.matrix.sqr(m3)
      t = rt_mx_ji.t().as_double()
      t = scitbx.matrix.col((t[0],t[1],t[2]))
      xyzs2 = unit_cell.orthogonalize(m3.elems*xyzs2+t)
      rg2.atoms().set_xyz(xyzs2)
      for atom in rg2.atoms():
        #if atom.name==atom2.name:
        if atom.name==atom2.name and atom.parent().altloc == atom2.parent().altloc:
          atom2=atom
          break
    return rg1, rg2, atom1, atom2


  def _is_clash(self,
                i_seq,
                j_seq,
                fsc0,
                model_distance):
    """
    Determine if a nonbonded proxy is a clash.

    Parameters:
      i_seq (int): atom i_seq
      j_seq (int): atom i_seq
      fsc0 (dict of lists of int): dictionary with a list of all atoms connected to an atom
      model_distance (float): distance between atom i and atom j

    Returns:
      bool (is_clash): if a nonbonded proxy is a clash
    """
    is_clash = False

    # ignore overlaps of atoms with occupancy sum<1 and in different chains
    # a couple of models has asym unit content with superposed chains
#    atom_i = self.atoms[i_seq]
#    atom_j = self.atoms[j_seq]
#    if atom_i.occ + atom_j.occ <= 1.0:
#      if atom_i.chain != atom_j.chain:
#        return False

    # Exclude 1-5 interaction of H atom and heavy atom
    is_1_5_interaction = check_if_1_5_interaction(
             i_seq = i_seq,
             j_seq = j_seq,
             hd_sel = self.hd_sel,
             full_connectivity_table = fsc0)
    if not is_1_5_interaction:
      #if i_seq > j_seq:
      #  i_seq, j_seq = j_seq, i_seq
      # Check to prevent that symmetry clashes are counted twice
      #if (i_seq, j_seq) not in self._clashes_dict.keys():
      is_clash = True
      if (i_seq not in self._mult_clash_dict): self._mult_clash_dict[i_seq] = list()
      if (j_seq not in self._mult_clash_dict): self._mult_clash_dict[j_seq] = list()
      self._mult_clash_dict[i_seq].append(j_seq)
      self._mult_clash_dict[j_seq].append(i_seq)

    return is_clash


  def _process_clashes(self, sites_cart, fsc0):
    """
    Process clashes from previous loop through nonbonded_proxies.

    This step is necessary to filter out clashes with common atoms.
    X-H ~~~ Y might produce two clashes, one between X and Y, the other
    between H and Y. This step filters the raw results and keeps the shorter
    of the two clashes (if an angular cutoff is above a limit)
    """
    clashes_to_be_removed = list()
    for i_seq, j_seq_list in six.iteritems(self._mult_clash_dict):
      n_multiples = len(j_seq_list)
      if n_multiples <= 1: continue
      for i in range(n_multiples-1):
        for j in range(i+1, n_multiples):
          multiple_1 = j_seq_list[i]
          multiple_2 = j_seq_list[j]
          cos_angle = 0
        # test inline only if the two atoms that overlap with the common atom are connected
          if multiple_1 in fsc0[multiple_2]:
            atom_1_xyz = sites_cart[multiple_1]
            atom_2_xyz = sites_cart[multiple_2]
            atom_i_xyz = sites_cart[i_seq]
            tuple1 = [i_seq, multiple_1]
            tuple2 = [i_seq, multiple_2]
            tuple1.sort()
            tuple2.sort()
            tuple1 = tuple(tuple1)
            tuple2 = tuple(tuple2)
            # Don't check for inline if symmetry overlap (needs correcty xyz!)
            if not self._clashes.iseq_tuple_is_sym_clash(tuple1):
              cos_angle = cos_vec(atom_1_xyz, atom_2_xyz, atom_i_xyz)
            # check if atoms are inline
            if abs(cos_angle) > 0.707 and (atom_1_xyz != atom_2_xyz):
              if (self._clashes.iseq_tuple_is_clashing(tuple1) and
                  self._clashes.iseq_tuple_is_clashing(tuple2)):
              #if tuple1 in self._clashes_dict and tuple2 in self._clashes_dict:
                if (self._clashes.get_model_distance(tuple1) <
                   self._clashes.get_model_distance(tuple2)):
                  clashes_to_be_removed.append(tuple2)
                else:
                  clashes_to_be_removed.append(tuple1)
    for clash_tuple in clashes_to_be_removed:
      if self._clashes.iseq_tuple_is_clashing(clash_tuple):
        self._clashes.remove_clash(clash_tuple)
#    double_tuples = list()
#    tuples = self._clashes_dict.keys()
#    # Now filter out doubly counted clashes (due to symmetry)
#    for clash_tuple in tuples:
#      i_seq, j_seq = clash_tuple[0], clash_tuple[1]
#      if (j_seq, i_seq) in tuples:
#        if i_seq > j_seq:
#          double_tuples.append(clash_tuple)
#    for clash_tuple in double_tuples:
#      del self._clashes_dict[clash_tuple]
#

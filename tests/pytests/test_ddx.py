import psi4
import pytest
import numpy as np

from psi4 import core

from utils import *
from addons import using, uusing

pytestmark = [pytest.mark.psi, pytest.mark.api]

__geoms = {
    "benzene":
    """
    C -0.886454    0.338645    0.000000
    C  0.508706    0.338645    0.000000
    C  1.206244    1.546396    0.000000
    C  0.508590    2.754905   -0.001199
    C -0.886235    2.754827   -0.001678
    C -1.583836    1.546621   -0.000682
    H -1.436213   -0.613672    0.000450
    H  1.058214   -0.613868    0.001315
    H  2.305924    1.546476    0.000634
    H  1.058790    3.707048   -0.001258
    H -1.436357    3.707108   -0.002631
    H -2.683440    1.546804   -0.000862
    symmetry c1
    units angstrom
    """,
    "fcm":
    """
    C   -0.502049    0.594262    0.000000
    H   -0.145376    1.098660    0.873652
    H   -1.572049    0.594275    0.000000
    Cl   0.084628    1.423927   -1.437034
    F   -0.052065   -0.678535    0.000000
    symmetry c1
    units angstrom
    """,
    "h2o":
    """
    O -0.966135 0.119522 0
    H -0.006135 0.119522 0
    H -1.286590 1.024458 0
    symmetry c1
    units angstrom
    """,
    "nh3":
    """
    N     -0.0000000001    -0.1040380466      0.0000000000
    H     -0.9015844116     0.4818470201     -1.5615900098
    H     -0.9015844116     0.4818470201      1.5615900098
    H      1.8031688251     0.4818470204      0.0000000000
    symmetry c1
    no_reorient
    no_com
    units bohr
    """,
    "h2":
    """
    H 0 0 0.5
    H 0 0 -0.5
    symmetry c1
    units angstrom
    """,
    "h":
    """
    H 0 0 0
    1 1
    symmetry c1
    units angstrom
    """,
}


def _base_test_fock(fock_term, density_matrix, eps=1e-4, tol=1e-8):
    E, V = fock_term(density_matrix)

    perturbation = np.random.random(density_matrix.np.shape)
    perturbation = perturbation + perturbation.T
    delta = np.sum(V.np * perturbation)

    Em, _ = fock_term(core.Matrix.from_array(density_matrix.np - eps * perturbation))
    Ep, _ = fock_term(core.Matrix.from_array(density_matrix.np + eps * perturbation))
    delta_ref = (Ep - Em) / (2 * eps)

    assert abs(delta - delta_ref) < tol


@pytest.mark.smoke
@pytest.mark.quick
@uusing("ddx")
@pytest.mark.parametrize("inp", [
   pytest.param({
       "geom": __geoms["h"],
       "dm": core.Matrix.from_array(np.array([[0.]])),
       "ddx": {"model": "cosmo", "solvent_epsilon": 1e8, "eta": 0, "radii": [1.0]},
       "ref": -0.2645886054599999,  # from Gaussian
   }, id='h'),
   pytest.param({
       "geom": __geoms["h2"],
       "dm": core.Matrix.from_array(0.6682326961201372 * np.ones((2, 2))),
       "ddx": {"model": "cosmo", "solvent_epsilon": 1e8, "eta": 0, "radii": [1.5873, 1.5873]},
       "ref": -0.0002016948,  # from Gaussian
   }, id='h2cosmo'),
   pytest.param({
       "geom": __geoms["h2"],
       "dm": core.Matrix.from_array(0.6682326961201372 * np.ones((2, 2))),
       "ddx": {"model": "pcm", "solvent_epsilon": 80, "radii": [1.5873, 1.5873]},
   }, id='h2pcm'),
   pytest.param({
       "geom": __geoms["h2"],
       "dm": core.Matrix.from_array(0.6682326961201372 * np.ones((2, 2))),
       "ddx": {"model": "lpb", "solvent_epsilon": 80, "solvent_kappa": 1.5,
               "radii": [1.5873, 1.5873]},
   }, id='h2lpb'),
])
def test_ddx_fock_build(inp):
    """
    Tests COSMO / LPB energy against reference from Gaussian
    and internal consistency of Fock matrix versus the energy.
    """
    from psi4.driver.procrouting.solvent import ddx

    psi4.set_options({
        "df_scf_guess": False,
        #
        "ddx_lmax": 3,
        "ddx_n_lebedev": 302,
        "ddx_solute_spherical_points": 350,
        "ddx_solute_radial_points": 99,
    })
    for key in inp["ddx"].keys():
        psi4.set_options({"ddx_" + key: inp["ddx"][key]})

    # build the DDX object to test
    mol = psi4.geometry(inp["geom"])
    basis = psi4.core.BasisSet.build(mol, "BASIS", "sto-3g")
    ddx_options = ddx.get_ddx_options(mol)
    ddx_iface = ddx.DdxInterface(mol, ddx_options, basis)

    def get_EV(density_matrix):
        E, V, _ = ddx_iface.get_solvation_contributions(density_matrix)
        return E, V

    _base_test_fock(get_EV, inp["dm"], tol=1e-8)

    if "ref" in inp:
        E, _ = get_EV(inp["dm"])
        assert compare_values(inp["ref"], E, atol=1e-16, rtol=1e-2)

@pytest.mark.quick
@uusing("ddx")
def test_ddx_limiting_cases():
    """Test consistency of limiting cases in PCM / COSMO / LPB"""
    from psi4.driver.procrouting.solvent import ddx

    psi4.set_options({
        "df_scf_guess": False,
        "ddx_lmax": 20,
        "ddx_n_lebedev": 590,
        "ddx_solute_spherical_points": 590,
        "ddx_solute_radial_points": 100,
        "ddx_shift": 0.0,
        "ddx_eta": 0.1,
        "ddx_radii_scaling": 7.1,
        "basis": "3-21g",
        "ddx": False,
    })

    # get a realistic guess density
    mol = psi4.geometry(__geoms["nh3"])
    basis = psi4.core.BasisSet.build(mol, "BASIS", "sto-3g")
    _, wfn = psi4.energy('SCF', molecule=mol, return_wfn=True)
    density_matrix = core.Matrix.from_array(wfn.Da().np)

    def ddenergy(model, solvent_kappa=0.0, solvent_epsilon=80.0):
        psi4.set_options({"ddx_solvent_kappa": solvent_kappa, "ddx_model": model,
                          "ddx_solvent_epsilon": solvent_epsilon, "ddx_solvation_convergence": 1e-10})
        ddx_options = ddx.get_ddx_options(mol)
        ddx_iface = ddx.DdxInterface(mol, ddx_options, basis)
        E, V, _ = ddx_iface.get_solvation_contributions(density_matrix)
        if model == "cosmo":
            fepsilon = (solvent_epsilon - 1) / solvent_epsilon
            E = E / fepsilon
            V.scale(fepsilon)
        return E, V

    e_pcminf, v_pcminf = ddenergy("pcm", solvent_epsilon=1e12)
    e_pcm, v_pcm = ddenergy("pcm", solvent_epsilon=80.0)
    e_cosmo, v_cosmo = ddenergy("cosmo", solvent_epsilon=1e12)

    e_lpb_einf, v_lpb_einf = ddenergy("lpb", solvent_kappa=0.1, solvent_epsilon=1e12)
    e_lpb0, v_lpb0 = ddenergy("lpb", solvent_kappa=1e-5, solvent_epsilon=80.0)
    e_lpbinf, v_lpbinf = ddenergy("lpb", solvent_kappa=10, solvent_epsilon=80.0)

    assert abs(e_pcminf - e_cosmo)    / abs(e_cosmo)    < 1e-10  # noqa: E221
    assert abs(e_pcminf - e_lpb_einf) / abs(e_lpb_einf) < 1e-10  # noqa: E221
    assert abs(e_cosmo  - e_lpb_einf) / abs(e_lpb_einf) < 1e-10  # noqa: E221
    assert abs(e_lpb0   - e_pcm)      / abs(e_pcm)      < 1e-5   # noqa: E221
    assert abs(e_lpbinf - e_lpb_einf) / abs(e_lpb_einf) < 1e-4   # noqa: E221
    assert abs(e_lpbinf - e_cosmo)    / abs(e_cosmo)    < 1e-4   # noqa: E221
    assert abs(e_lpbinf - e_pcminf)   / abs(e_pcminf)   < 1e-4   # noqa: E221

    assert np.max(np.abs(v_pcminf.np - v_cosmo.np))    < 1e-10   # noqa: E221
    assert np.max(np.abs(v_pcminf.np - v_lpb_einf.np)) < 1e-10   # noqa: E221
    assert np.max(np.abs(v_cosmo.np  - v_lpb_einf.np)) < 1e-10   # noqa: E221
    assert np.max(np.abs(v_lpb0.np   - v_pcm.np))      < 1e-5    # noqa: E221
    assert np.max(np.abs(v_lpbinf.np - v_lpb_einf.np)) < 1e-4    # noqa: E221
    assert np.max(np.abs(v_lpbinf.np - v_cosmo.np))    < 1e-4    # noqa: E221
    assert np.max(np.abs(v_lpbinf.np - v_pcminf.np))   < 1e-4    # noqa: E221


@pytest.mark.quick
@uusing("ddx")
@pytest.mark.parametrize("inp", [
    pytest.param({
        "geom": __geoms["h2o"],
        "ddx": {"solvent_epsilon": 1e8, "eta": 0, },
        "ref": -75.5946789010,  # from Gaussian
        "solvation": -0.009402,
    }, id='h2o'),
    #
    pytest.param({
        "geom": __geoms["fcm"],
        "ddx": {"solvent_epsilon": 1e8, "eta": 0, },
        "ref": -594.993575419,  # from Gaussian
        "solvation": -0.006719,
    }, id='fcm'),
    #
    pytest.param({
        "geom": __geoms["fcm"],
        "ddx": {"solvent_epsilon": 2.0, "eta": 0, },
        "ref": -594.990420855,  # from Gaussian
        "solvation": -0.002964,
    }, id='fcmeps'),
    #
    pytest.param({
        "geom": __geoms["fcm"],
        "ddx": {"solvent_epsilon": 2.0, "eta": 0.2, },
        "ref": -594.990487330,  # from Gaussian
        "solvation": -0.003041,
    }, id='fcmepseta'),
    #
    pytest.param({
        "geom": __geoms["benzene"],
        "ddx": {"solvent_epsilon": 1e8, "eta": 0, },
        "ref": -229.420391688,  # from Gaussian
        "solvation": -0.005182,
    }, id='benzene'),
])
def test_ddx_rhf_reference(inp):
    mol = psi4.geometry(inp["geom"])
    psi4.set_options({
        "ddx": True,
        "basis": "3-21g",
        "guess": "core",
        "scf_type": "direct",
        #
        "ddx_model": "cosmo",
        "ddx_radii_set": "uff",
        "ddx_lmax": 3,
        "ddx_n_lebedev": 302,
        "ddx_solute_spherical_points": 302,
        "ddx_solute_radial_points": 75,
        "ddx_shift": 0.0,
    })
    for key in inp["ddx"].keys():
        psi4.set_options({"ddx_" + key: inp["ddx"][key]})
    scf_e, wfn = psi4.energy('SCF', return_wfn=True, molecule=mol)
    ddx_e = wfn.scalar_variable("dd solvation energy")

    assert compare_values(inp["solvation"], ddx_e, 4, "DDX solvation energy versus Gaussian")
    assert compare_values(inp["ref"], scf_e, 4, "Total SCF energy with DDX versus Gaussian")


@pytest.mark.quick
@uusing("ddx")
@pytest.mark.parametrize("inp", [
    pytest.param({
        "geom": __geoms["h2o"],
        "basis": "cc-pvdz",
        "ddx": {"model": "cosmo", "solvent": "water", "radii_set": "bondi", },
        "ref": -76.0346355428018,
    }, id='h2o-cosmo'),
    pytest.param({
        "geom": __geoms["fcm"],
        "basis": "cc-pvdz",
        "ddx": {"model": "pcm", "solvent": "water", "radii_set": "uff", },
        "ref": -597.9718943192062,
    }, id='fcm-pcm'),
    pytest.param({
        "geom": __geoms["nh3"],
        "basis": "cc-pvdz",
        "ddx": {"model": "lpb", "solvent": "water", "radii_set": "uff", "solvent_kappa": 0.11},
        "ref": -56.1988043810054,
    }, id='nh3-lpb'),
])
def test_ddx_rhf_consistency(inp):
    mol = psi4.geometry(inp["geom"])
    psi4.set_options({
        "ddx": True,
        "basis": inp["basis"],
        #
        "ddx_lmax": 10,
        "ddx_n_lebedev": 302,
        "ddx_solute_spherical_points": 302,
        "ddx_solute_radial_points": 75,
    })
    for key in inp["ddx"].keys():
        psi4.set_options({"ddx_" + key: inp["ddx"][key]})
    scf_e, wfn = psi4.energy('SCF', return_wfn=True, molecule=mol)
    assert compare_values(inp["ref"], scf_e, 8, "Total SCF energy with DDX versus reference data")


@uusing("ddx")
@pytest.mark.parametrize("scf_type", ["pk", "out_of_core", "direct", "df", "cd"])
def test_ddx_eri_algorithms(scf_type):
    mol = psi4.geometry(__geoms["nh3"])
    psi4.set_options({
        "scf_type": scf_type,
        "basis": "6-31g",
        "ddx": True,
        "ddx_model": "pcm",
        "ddx_solvent": "water",
        "ddx_radii_set": "uff",
    })
    if scf_type in ("df", "cd"):
        tol = 4
    else:
        tol = 9

    ref = -56.171546236617495
    scf_e = psi4.energy('SCF')
    assert compare_values(ref, scf_e, tol, "Total SCF energy with DDX versus reference data")

@pytest.mark.quick
@uusing("ddx")
def test_ddx_tdscf_pcmsolver():
    # PCMsolver reference values, same as in tests/pcmsolver/tdscf
    exc_energies = np.array([  # Hartree
        0.08972598844884663,
        0.2719972189552112,
        0.33525624703045037,
        0.3713900898382711,
        0.3762084431466903,
    ])

    osc_strengths = np.array([
        0.00414272407997719,
        4.590977316768732e-28,
        0.005715258102198367,
        0.018432750255865125,
        0.006434117688452513,
    ])

    scf_ref = -55.5218518303635165

    psi4.geometry("""
        0, 2
        N  0.000000000000     0.000000000000    -0.079859033927
        H  0.000000000000    -0.803611003426     0.554794694632
        H  0.000000000000     0.803611003426     0.554794694632
        symmetry c1
        units angstrom
        """)

    psi4.set_options({
        "reference":      "uhf",
        "scf_type":       "pk",
        "basis":          "def2-SVP",
        "e_convergence":  10,
        "maxiter":        50,
        "tdscf_states":   5,
        #
        "ddx":            True,
        "ddx_model":      "pcm",
        "ddx_solvent":    "water",
        "ddx_radii_set":  "uff",   # Make it compatible with pcmsolver
        'ddx_radii_scaling': 1.2,  # Make it compatible with pcmsolver
    })

    scf_e = psi4.energy("TD-SCF")
    assert compare_values(scf_ref, scf_e, 4, "Total SCF energy with DDX versus reference data")

    f_calc = []
    e_calc = []
    for i in range(5):
        e_calc.append(psi4.variable(f'TD-HF ROOT 0 -> ROOT {i+1} EXCITATION ENERGY - A TRANSITION'))
        f_calc.append(psi4.variable(f'TD-HF ROOT 0 -> ROOT {i+1} OSCILLATOR STRENGTH (LEN) - A TRANSITION'))
    assert compare_arrays(exc_energies, e_calc, 0.0005, 'PCM EXCITATION ENERGY ')
    assert compare_arrays(osc_strengths, f_calc, 0.0005, 'PCM OSCILLATOR STRENGTH ')


@pytest.mark.quick
@uusing("ddx")
def test_ddx_tdscf_gaussian():
    # Reference test against Gaussian
    exc_energies = np.array([  # eV
        9.7131, 11.6679, 11.9693, 14.0604, 16.0886, 20.3350, 33.4852, 34.1673, 35.3953, 35.6058,
    ])
    exc_energies /= psi4.constants.conversion_factor('hartree', 'eV')

    psi4.geometry("""
        O         0.00000000     0.00000000     0.11721877
        H         0.00000000     1.48123757    -0.93017349
        H         0.00000000    -1.48123757    -0.93017349
        0 1
        symmetry c1
        no_reorient
        no_com
        units bohr
    """)
    psi4.set_options({
        "basis": "3-21g",
        "d_convergence": 1e-8,
        "e_convergence": 1e-12,
        "tdscf_r_convergence": 1e-6,
        "scf_type": "direct",
        "guess": "core",
        "ddx": True,
        "tdscf_states": 10,
        "ddx_lmax": 10,
        "ddx_n_lebedev": 590,
        "ddx_model": "pcm",
        "ddx_radii_set": "uff",
        "ddx_radii_scaling": 1.1,
        "ddx_eta": 0.0,
        "ddx_solvation_convergence": 1e-10,
        "ddx_solvent_epsilon": 2.0,
        "ddx_solvent_epsilon_optical": 2.0,
        "ddx_solute_spherical_points": 590,
        "ddx_solute_radial_points": 1000,
    })
    psi4.energy('TD-HF')

    e_calc = []
    for i in range(5):
        e_calc.append(psi4.variable(f'TD-HF ROOT 0 -> ROOT {i+1} EXCITATION ENERGY - A TRANSITION'))
    assert compare_values(exc_energies[:5], e_calc, 'PCM EXCITATION ENERGY ', atol=0.0001)

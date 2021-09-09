from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Union, List, Tuple

import numpy as np

from grid_resources.commodities import Fuel
from grid_resources.technologies import (
    TechnoEconomicProperties,
    EmissionsCharacteristics,
    GridTechnology,
    InstalledTechnology
)
from utils.geometry import Line


@dataclass
class GeneratorTechnoEconomicProperties(TechnoEconomicProperties):
    thermal_efficiency: float
    max_capacity_factor: float
    carbon_capture: float
    emissions: EmissionsCharacteristics
    fuel: Fuel

    @property
    def fuel_cost_per_energy(self):
        return self.fuel.price / self.thermal_efficiency

    @property
    def total_var_cost(self) -> float:
        return self.variable_om + \
               self.emissions.tariff.price + \
               self.fuel_cost_per_energy

    @staticmethod
    def from_dict(
            name: str,
            data: Dict[str, Union[str, float]],
            fuels: Dict[str, Fuel],
            emissions_tariff,
            interest_rate
    ):
        fuel = fuels[data['fuel']]
        emissions = EmissionsCharacteristics(
            data['emission_rate'],
            'tonnes / MWh',
            emissions_tariff
        )
        del data['fuel']
        del data['emission_rate']

        return GeneratorTechnoEconomicProperties(
            name,
            resource_class='generator',
            fuel=fuel,
            emissions=emissions,
            interest_rate=interest_rate,
            **data
        )


@dataclass
class GeneratorTechnology(GridTechnology):
    properties: GeneratorTechnoEconomicProperties

    @property
    def annual_cost_curve(self) -> Line:
        """Get linear cost curve based on total var and fixed annual costs
        """
        return Line(
            self.properties.total_var_cost,
            self.properties.total_fixed_cost,
            name=self.name
        )

    def get_period_cost(self, period) -> float:
        """ Returns the unit cost per capacity of a resource running
            over a period of time (expressed as years)
        """
        return self.annual_cost_curve.find_y_at_x(period)

    def intercept_x_vals(
            self,
            other_generators: List[GeneratorTechnology]
    ) -> List[Tuple[GeneratorTechnology, float]]:
        """
        Finds the x-coordinates of intercepts between self and another Lines
        Only between 0 and 1 years
        Parallel lines have no intercept
        """
        intercept_list = list()
        for generator in other_generators:
            intercept = self.annual_cost_curve.find_intercept_on_line(
                generator.annual_cost_curve
            )
            if intercept.x:
                intercept_list.append((generator, intercept.x))
        return intercept_list


@dataclass(order=True)
class InstalledGenerator(InstalledTechnology):
    technology: GeneratorTechnology
    constraint: Union[float, np.ndarray] = None

    def dispatch(
            self,
            demand: np.ndarray
    ) -> np.ndarray:
        if self.constraint:
            constraint = self.constraint
        else:
            constraint = self.capacity

        return np.clip(
            demand,
            0,
            constraint
        )

    def annual_dispatch_cost(self, dispatch: np.ndarray) -> float:
        total_dispatch = dispatch.sum()
        return total_dispatch * self.technology.properties.total_var_cost + \
               self.capacity * self.technology.properties.total_fixed_cost

    def levelized_cost(
            self,
            dispatch: np.ndarray,
            total_dispatch_cost: float = None
    ) -> float:
        """ Get levelised cost of energy based on annual dispatch curve
        """
        if not total_dispatch_cost:
            total_dispatch_cost = self.annual_dispatch_cost(dispatch)
        return total_dispatch_cost / dispatch.sum()

    def hourly_dispatch_cost(
            self,
            dispatch: np.ndarray,
            total_dispatch_cost: float = None,
            levelized_cost: float = None,
    ) -> np.ndarray:
        """ Get hourly dispatch cost based on lcoe
        """
        if not total_dispatch_cost:
            total_dispatch_cost = self.annual_dispatch_cost(dispatch)
        if not levelized_cost:
            levelized_cost = self.levelized_cost(dispatch, total_dispatch_cost)
        return dispatch * levelized_cost
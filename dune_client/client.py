""""
Basic Dune Client Class responsible for refreshing Dune Queries
Framework built on Dune's API Documentation
https://duneanalytics.notion.site/API-Documentation-1b93d16e0fa941398e15047f643e003a
"""
from __future__ import annotations

import logging.config
import time
from json import JSONDecodeError
from typing import Any

import requests
from requests import Response

from dune_client.interface import DuneInterface
from dune_client.models import (
    ExecutionResponse,
    DuneError,
    ExecutionStatusResponse,
    ResultsResponse,
    ExecutionState,
)
from dune_client.types import DuneRecord
from dune_client.query import Query

log = logging.getLogger(__name__)
logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s %(message)s", level=logging.DEBUG
)

BASE_URL = "https://api.dune.com/api/v1"


class DuneClient(DuneInterface):
    """
    An interface for Dune API with a few convenience methods
    combining the use of endpoints (e.g. refresh)
    """

    def __init__(self, api_key: str):
        self.token = api_key

    @staticmethod
    def _handle_response(
        response: Response,
    ) -> Any:
        try:
            # Some responses can be decoded and converted to DuneErrors
            response_json = response.json()
            log.debug(f"received response {response_json}")
            return response_json
        except JSONDecodeError as err:
            # Others can't. Only raise HTTP error for not decodable errors
            response.raise_for_status()
            raise ValueError("Unreachable since previous line raises") from err

    def _get(self, url: str) -> Any:
        log.debug(f"GET received input url={url}")
        response = requests.get(url, headers={"x-dune-api-key": self.token}, timeout=10)
        return self._handle_response(response)

    def _post(self, url: str, params: Any) -> Any:
        log.debug(f"POST received input url={url}, params={params}")
        response = requests.post(
            url=url, json=params, headers={"x-dune-api-key": self.token}, timeout=5
        )
        return self._handle_response(response)

    def execute(self, query: Query) -> ExecutionResponse:
        """Post's to Dune API for execute `query`"""
        response_json = self._post(
            url=f"{BASE_URL}/query/{query.query_id}/execute",
            params={
                "query_parameters": {
                    p.key: p.to_dict()["value"] for p in query.parameters()
                }
            },
        )
        try:
            return ExecutionResponse.from_dict(response_json)
        except KeyError as err:
            raise DuneError(response_json, "ExecutionResponse", err) from err

    def get_status(self, job_id: str) -> ExecutionStatusResponse:
        """GET status from Dune API for `job_id` (aka `execution_id`)"""
        response_json = self._get(
            url=f"{BASE_URL}/execution/{job_id}/status",
        )
        try:
            return ExecutionStatusResponse.from_dict(response_json)
        except KeyError as err:
            raise DuneError(response_json, "ExecutionStatusResponse", err) from err

    def get_result(self, job_id: str) -> ResultsResponse:
        """GET results from Dune API for `job_id` (aka `execution_id`)"""
        response_json = self._get(url=f"{BASE_URL}/execution/{job_id}/results")
        try:
            return ResultsResponse.from_dict(response_json)
        except KeyError as err:
            raise DuneError(response_json, "ResultsResponse", err) from err

    def cancel_execution(self, job_id: str) -> bool:
        """POST Execution Cancellation to Dune API for `job_id` (aka `execution_id`)"""
        response_json = self._post(
            url=f"{BASE_URL}/execution/{job_id}/cancel", params=None
        )
        try:
            # No need to make a dataclass for this since it's just a boolean.
            success: bool = response_json["success"]
            return success
        except KeyError as err:
            raise DuneError(response_json, "CancellationResponse", err) from err

    def refresh(self, query: Query, ping_frequency: int = 5) -> list[DuneRecord]:
        """
        Executes a Dune `query`, waits until execution completes,
        fetches and returns the results.
        Sleeps `ping_frequency` seconds between each status request.
        """
        job_id = self.execute(query).execution_id
        state = self.get_status(job_id).state
        while state != ExecutionState.COMPLETED:
            print(
                f"waiting for query execution {job_id} to complete: current state {state}"
            )
            log.info(
                f"waiting for query execution {job_id} to complete: current state {state}"
            )
            time.sleep(ping_frequency)
            state = self.get_status(job_id).state

        full_response = self.get_result(job_id)
        assert (
            full_response.result is not None
        ), f"Expected Results on completed execution status {full_response}"
        return full_response.result.rows

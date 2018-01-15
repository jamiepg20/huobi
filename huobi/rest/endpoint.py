""" Endpoint and HuobiRestResult class
"""
from datetime import datetime
from urllib.parse import urlparse, parse_qsl, quote, urlencode

from huobi.rest.helper import REQUIRED_HEADERS, REQUIRED_POST_HEADERS
from huobi.rest.error import (
    HuobiRestError,
    HuobiRestRequstError,
    HuobRestiApiError,
    HuobiRestArgumentError,
    HuobiRestApiDecodeError
)
from huobi.utils import hmac_sha256_base64


class HuobiRestEndpointResult(object):
    """
    Huobi Rest Endpoint Result
    """

    def __init__(self, req, res, data):
        self.req = req
        self.res = res
        self.data = data


class Endpoint(object):
    """
    Endpoint class
    """

    def __init__(self, method, path, params=None, auth_required=True):
        self.method = method
        self.path = path
        self.auth_required = auth_required
        self.params = params or {}
        self.attr_name = None

    @staticmethod
    def _sign_url(instance, method: str, url: str):
        additonal_qs = {
            'AccessKeyId': instance.access_key,
            'SignatureMethod': 'HmacSHA256',
            'SignatureVersion': '2',
            'Timestamp': datetime.utcnow().isoformat(timespec='seconds')
        }
        url_obj = urlparse(url)
        qs_items = parse_qsl(url_obj.query) + list(additonal_qs.items())
        qs_string = '&'.join([
            f'{k}={value}'
            for k, value in sorted(qs_items)
        ])
        msg = f'{method.upper()}\n{url_obj.netloc}\n{url_obj.path}{qs_string}'
        msg = msg.strip()
        signature = quote(hmac_sha256_base64(instance.secret_key, msg))
        new_qs_dict = {**dict(qs_items), 'Signature': signature}
        new_url = (
            f'{url_obj.scheme}://{url_obj.netloc}'
            f'{url_obj.path}?{urlencode(new_qs_dict)}'
        )
        return new_url

    @staticmethod
    def _handle_response(_instance, res):
        try:
            res.raise_for_status
        except Exception as exc:
            raise HuobiRestRequstError('Request Error') from exc
        try:
            json_data = res.json()
        except Exception as exc:
            raise HuobiRestApiDecodeError('Json decode error') from exc

        if not json_data.get('status') == 'ok':
            error_code = json_data.get('err-code', 'Unknown error code')
            error_msg = json_data.get('err-msg', 'Unknow error message')
            raise HuobRestiApiError(
                f'{error_code}: {error_msg} \n'
                f'{res.request.method}: {res.request.url}'
            )

        return HuobiRestEndpointResult(res.request, res, json_data)

    def __get__(self, instance, owner):

        self.attr_name = next(
            k for k, v in owner.__dict__.items() if v == self
        ) or 'wrapper'

        if self.auth_required and (
                not instance.secret_key or not instance.access_key):
            raise HuobiRestError(f'{self.attr_name}')

        def _wrapper(**kwargs):
            query_params = {}
            for param_name, param_spec in self.params.items():
                required = param_spec.get('required', False)
                choices = param_spec.get('choices', None)
                if required and (
                        'default' not in param_spec
                ) and not kwargs.get(param_name):
                    raise HuobiRestArgumentError(
                        f'{param_name} is required in {self.attr_name}'
                    )
                param_value = kwargs.get(
                    param_name,
                    param_spec.get('default')
                )
                if choices and param_value and param_value not in choices:
                    raise HuobiRestArgumentError(
                        f'{param_value} is not a'
                        f'valid value for {param_name} \n'
                        f'Choices are {choices}')
                if param_name is not None:
                    query_params[param_name] = param_value

            url = f'{instance.base_url}{self.path}'
            res = None
            if self.method.lower() == 'get':
                url = f'{url}?{urlencode(query_params)}'
                url = self._sign_url(instance, 'GET', url)
                try:
                    res = instance.session.get(url, headers=REQUIRED_HEADERS)
                except Exception as exc:
                    raise HuobiRestRequstError('Request error') from exc
            if self.method.lower() == 'post':
                url = self._sign_url(instance, 'POST', url)
                try:
                    res = instance.session.post(
                        url,
                        body=kwargs['body'],
                        headers=REQUIRED_POST_HEADERS
                    )
                except Exception as exc:
                    raise HuobiRestRequstError('Request error') from exc

            return self._handle_response(instance, res)

        _wrapper.__name__ = self.attr_name

        return _wrapper
"""Default pagination for every list endpoint.

Enforces a sane page size and a hard maximum so that no future list endpoint
can accidentally return thousands of rows in one response. Clients may request
a different size via ``?page_size=`` up to ``max_page_size``.
"""
from rest_framework.pagination import PageNumberPagination


class DefaultPagination(PageNumberPagination):
    page_size = 25
    page_size_query_param = "page_size"
    max_page_size = 100

from django.core.validators import RegexValidator
from django.db import models


class Counterparty(models.Model):
    name = models.CharField('Название', max_length=255, unique=True)

    class Meta:
        db_table = 'counterparties'
        ordering = ['name']
        verbose_name = 'контрагент'
        verbose_name_plural = 'контрагенты'

    def __str__(self):
        return self.name


class CollectionAgency(models.Model):
    name = models.CharField('Название', max_length=255, unique=True)
    shortname = models.CharField('Краткое наименование', max_length=100, blank=True)

    class Meta:
        db_table = 'collection_agencies'
        ordering = ['name', 'pk']
        verbose_name = 'коллекторское агентство'
        verbose_name_plural = 'коллекторские агентства'

    def __str__(self):
        return self.name


class Creditor(models.Model):
    name = models.CharField('Наименование', max_length=255, unique=True)
    bin = models.CharField('БИН', max_length=12, blank=True, validators=[RegexValidator(r'^\d{12}$', 'БИН должен содержать 12 цифр.')])
    class Meta:
        db_table = 'imports_creditor'
        ordering = ('name',)
        verbose_name_plural = 'Первичные кредиторы'
    def __str__(self):
        return self.name


class Cession(models.Model):
    number = models.CharField('Номер договора', max_length=100)
    date = models.DateField('Дата договора')
    creditor = models.ForeignKey('references.Creditor', on_delete=models.PROTECT, verbose_name='Первичный кредитор')
    class Meta:
        db_table = 'imports_cession'
        ordering = ('number',)
        constraints = [models.UniqueConstraint(fields=('number', 'date', 'creditor'), name='unique_cession')]
        verbose_name_plural = 'Договоры цессии'
    def __str__(self):
        return f'{self.number} от {self.date:%d.%m.%Y} — {self.creditor}'


class CompanyAccount(models.Model):
    number = models.CharField('Номер счёта', max_length=100, unique=True)
    agency = models.ForeignKey('references.CollectionAgency', on_delete=models.PROTECT, verbose_name='КА')
    class Meta:
        db_table = 'imports_companyaccount'
        ordering = ('number',)
        verbose_name_plural = 'Счета компаний'
    def __str__(self):
        return f'{self.number} — {self.agency}'


class ReferenceValue(models.Model):
    kind = models.CharField('Справочник', max_length=50, choices=[('region', 'Регионы'), ('kato', 'КАТО'), ('gender', 'Пол'), ('document_type', 'Тип документа'), ('document_issuer', 'Орган выдачи'), ('writeoff_reason', 'Основания списания'), ('cancellation_reason', 'Основания отмены/удаления')])
    name = models.CharField('Значение', max_length=255)
    code = models.CharField('Код', max_length=50, blank=True)
    class Meta:
        db_table = 'imports_referencevalue'
        ordering = ('kind', 'name')
        constraints = [models.UniqueConstraint(fields=('kind', 'name'), name='unique_reference_value')]
    def __str__(self):
        return self.name

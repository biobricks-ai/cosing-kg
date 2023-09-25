#!/usr/bin/env perl
# PODNAME: csv-to-rdf.pl
# ABSTRACT: Processes CosIng CSV to RDF

use v5.38;

# Extra deps for loading purposes.
use Class::XSAccessor ();
use Type::Tiny::XS ();
use Text::CSV_XS ();

package Record {
	use Mu;
	use MooX::Should;
	use MooX::XSConstructor;
	use Devel::StrictMode qw(LAX);
	use Function::Parameters;
	use Attean;
	use Attean::RDF qw(iri literal triple);
	use Types::Common qw(ArrayRef PositiveInt StrMatch Maybe NonEmptyStr);
	use Types::Attean qw(AtteanIRI);
	use URI::NamespaceMap;
	use namespace::clean;

	use Type::Utils qw( declare as where message );

	my $map = URI::NamespaceMap->new( {
		'cosing' => 'http://example.org/cosing/',
		'cas'    => 'https://identifiers.org/cas/',
	} );

	my $TO_IRI = fun($this, $value = ) {
		if( $this isa 'Attean::IRI' ) {
			return $this;
		} elsif( $this isa 'IRI' ) {
			return Attean::IRI->new( value => $this->as_string, lazy => LAX );
		} elsif( $this isa 'URI::Namespace' && $value ) {
			return Attean::IRI->new( value => $this->as_string . $value, lazy => LAX );
		}
	};

	my %prop = (
		casNo    => $map->cosing->$TO_IRI('prop/casNo'),
		inciName => $map->cosing->$TO_IRI('prop/inciName'),
		function => $map->cosing->$TO_IRI('prop/function'),
	);

	my $cas_rn_re = qr/[1-9]\d{1,6}-\d{2}-\d/;
	# Not using the checksum. <https://www.wikidata.org/wiki/Property_talk:P231>
	my $CasRN_Str = declare as StrMatch[qr/\A$cas_rn_re\z/];

	ro cosing_ref_no => required => 1, isa => PositiveInt;
	lazy _cosing_ref_no_iri => method() {
		$map->cosing->$TO_IRI( "ref/@{[ $self->cosing_ref_no ]}"  )
	}, should => AtteanIRI;

	ro cas_numbers => isa => ArrayRef[$CasRN_Str],
		coerce => sub { defined $_[0] ? [ $_[0] =~ /\b$cas_rn_re\b/g ] : []; };
	lazy _cas_numbers_iri => method() {
		[ map { $map->cas->$TO_IRI( $_ ) } $self->cas_numbers->@* ]
	}, should => ArrayRef[AtteanIRI];

	ro inci_name => required => 1, isa => NonEmptyStr;

	ro function  => isa => Maybe[NonEmptyStr];
	lazy _function_literals => method() {
		defined $self->function ? [ map { literal($_) } split /,\s+?/, $self->function ] : [];
	}, should => ArrayRef;

	method TO_TRIPLES() {
		my @triples;

		push @triples, map {
			triple( $self->_cosing_ref_no_iri, $prop{casNo} , $_ )
		} $self->_cas_numbers_iri->@*;

		push @triples, map {
			triple( $self->_cosing_ref_no_iri, $prop{inciName} , literal($_) )
		} $self->inci_name;

		push @triples, map {
			triple( $self->_cosing_ref_no_iri, $prop{function} , $_ )
		} $self->_function_literals->@*;

		return \@triples;
	}
}

package Process {
	use autodie;
	use Mu;
	use Syntax::Construct qw(<<~);
	use Function::Parameters;
	use Path::Tiny;
	use Term::ProgressBar;
	use Data::TableReader;
	use Types::Common qw(PositiveInt NonEmptyStr);
	use namespace::clean;

	method run(@files) {
		die <<~EOF unless @files >= 2;
		Need input and output paths:

		  $0 input.csv... output.nt

		EOF

		my $output_path = pop @files;
		my $output_fh = path($output_path)->openw_utf8;

		while( my $file = shift @files ) {
			say STDERR "Reading from $file";
			my $reader = Data::TableReader->new(
				input => $file,
				on_validation_fail => 'die',
				fields => [
					{ name => 'cosing_ref_no'    , header => 'COSING Ref No'                 , required => 1, type => PositiveInt }  , 
					{ name => 'inci_name'        , header => 'INCI name'                     , required => 1, }  , 
					{ name => 'inn_name'         , header => 'INN name'                      , }  , 
					{ name => 'euro_pharmo_name' , header => 'Ph. Eur. Name'                 , }  , 
					{ name => 'cas_numbers'      , header => 'CAS No'                        , required => 1, }  , 
					{ name => 'ec_no'            , header => 'EC No'                         , }  , 
					{ name => 'description'      , header => 'Chem/IUPAC Name / Description' , }  , 
					{ name => 'restriction'      , header => 'Restriction'                   , }  , 
					{ name => 'function'         , header => 'Function'                      , }  , 
					{ name => 'update_date'      , header => 'Update Date'                   , }  , 
				],
				record_class => 'Record',
			);

			my $store = Attean->get_store('SimpleTripleStore')->new();

			my $it = $reader->iterator;
			my ($count, $max) = (0, 100);
			my $progress = Term::ProgressBar->new({ count => $max, remove => 1 });
			while( my $record = $it->() ) {
				$store->add_triple($_) for $record->TO_TRIPLES->@*;
				$progress->update( $it->progress*100 ) if not $count++ % 100; # every 100 records
			}
			$progress->update($max);

			say STDERR "Writing $file triples to $output_path";
			Attean->get_serializer( 'NTriples' )->serialize_iter_to_io( $output_fh, $store->get_triples );
		}
	}
}

Process->new->run( @ARGV );
